"""Tests for the ingest flow in wiki_core.ingest."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from wiki_core.ingest import run_ingest, MAX_SOURCE_SIZE, MIN_SOURCE_SIZE
from wiki_core.store import WikiStore


class TestRunIngest:
    """Test cases for run_ingest function."""

    def test_ingest_creates_pages(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that ingest creates pages from source document."""
        # Create a source file
        source_path = wiki_store.root / "raw" / "test-source.md"
        source_path.write_text("# Test Source\n\nThis is test content.")

        # Mock LLM response - return valid JSON string with escaped newlines
        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = '{"source_summary": "Test document summary", "pages": [{"path": "pages/test-entity.md", "content": "# Test Entity\\n\\nEntity content"}]}'

        summary, pages = run_ingest(source_path, wiki_store)

        assert summary == "Test document summary"
        assert "pages/test-entity.md" in pages
        assert (wiki_store.root / "pages/test-entity.md").exists()

    def test_ingest_logs_event(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that ingest logs the event."""
        source_path = wiki_store.root / "raw" / "log-test.md"
        source_path.write_text("# Log Test\nContent")

        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = '{"source_summary": "Summary", "pages": []}'

        summary, pages = run_ingest(source_path, wiki_store)

        log_content = wiki_store.log_path.read_text()
        assert "ingest" in log_content
        assert "log-test.md" in log_content

    def test_ingest_rebuilds_index(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that ingest rebuilds the index after creating pages."""
        source_path = wiki_store.root / "raw" / "index-test.md"
        source_path.write_text("# Index Test\nContent")

        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = '{"source_summary": "Summary", "pages": [{"path": "pages/index-entity.md", "content": "# Index Entity\\n\\nContent"}]}'

        summary, pages = run_ingest(source_path, wiki_store)

        index = wiki_store.read_index()
        assert "index-entity" in index.lower() or "Index Entity" in index

    def test_ingest_empty_pages_response(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test ingest when LLM returns no pages."""
        source_path = wiki_store.root / "raw" / "empty-test.md"
        source_path.write_text("# Empty Test\nContent")

        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = '{"source_summary": "Nothing to extract", "pages": []}'

        summary, pages = run_ingest(source_path, wiki_store)

        assert summary == "Nothing to extract"
        assert pages == []

    def test_ingest_multiple_pages(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test ingest creating multiple pages."""
        source_path = wiki_store.root / "raw" / "multi-test.md"
        source_path.write_text("# Multi Test\nContent")

        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = '''{
            "source_summary": "Multi entity doc",
            "pages": [
                {"path": "pages/entity1.md", "content": "# Entity 1\\nContent 1"},
                {"path": "pages/entity2.md", "content": "# Entity 2\\nContent 2"},
                {"path": "pages/entity3.md", "content": "# Entity 3\\nContent 3"}
            ]
        }'''

        summary, pages = run_ingest(source_path, wiki_store)

        assert len(pages) == 3
        assert all((wiki_store.root / p).exists() for p in pages)

    def test_ingest_with_existing_pages(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test ingest with existing wiki pages for context."""
        # Create existing page
        wiki_store.write_page(
            "pages/existing.md",
            "# Existing\n\nExisting content\n\nRelated:\n- [[New Entity]]",
        )
        wiki_store.rebuild_index()

        source_path = wiki_store.root / "raw" / "context-test.md"
        source_path.write_text("# Context Test\nContent")

        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = '{"source_summary": "Summary", "pages": [{"path": "pages/new-entity.md", "content": "# New Entity\\nContent"}]}'

        summary, pages = run_ingest(source_path, wiki_store)

        assert "pages/new-entity.md" in pages

    def test_ingest_invalid_json_response(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test ingest when LLM returns invalid JSON."""
        source_path = wiki_store.root / "raw" / "invalid-test.md"
        source_path.write_text("# Invalid Test\nContent")

        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = "Not valid JSON at all"

        with pytest.raises(Exception):  # extract_json will raise
            run_ingest(source_path, wiki_store)

    def test_ingest_with_schema(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that ingest includes schema in system prompt."""
        source_path = wiki_store.root / "raw" / "schema-test.md"
        source_path.write_text("# Schema Test\nContent")

        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = '{"source_summary": "Summary", "pages": []}'

        run_ingest(source_path, wiki_store)

        # Verify the call was made
        assert mock_llm_client.chat.completions.create.called
        call_args = mock_llm_client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        system_msg = messages[0]["content"]
        assert "schema" in system_msg.lower() or "convention" in system_msg.lower()

    def test_ingest_source_not_found(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test ingest with non-existent source file."""
        source_path = wiki_store.root / "raw" / "nonexistent.md"

        with pytest.raises(FileNotFoundError):
            run_ingest(source_path, wiki_store)

    def test_ingest_creates_parent_directories(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that ingest creates parent directories for pages."""
        source_path = wiki_store.root / "raw" / "nested-test.md"
        source_path.write_text("# Nested Test\nContent")

        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = '''{
            "source_summary": "Summary",
            "pages": [
                {"path": "pages/subdir/nested-entity.md", "content": "# Nested Entity\\nContent"}
            ]
        }'''

        summary, pages = run_ingest(source_path, wiki_store)

        assert (wiki_store.root / "pages" / "subdir").exists()
        assert (wiki_store.root / "pages" / "subdir" / "nested-entity.md").exists()


class TestIngestFileSizeValidation:
    """Test cases for file size validation in ingest."""

    def test_ingest_empty_file_rejected(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that empty files are rejected."""
        source_path = wiki_store.root / "raw" / "empty.md"
        source_path.write_text("")  # Empty file

        with pytest.raises(ValueError, match="empty or too small"):
            run_ingest(source_path, wiki_store)

    def test_ingest_file_too_large_rejected(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that files larger than MAX_SOURCE_SIZE are rejected."""
        source_path = wiki_store.root / "raw" / "large.md"
        # Create a file larger than MAX_SOURCE_SIZE (10MB)
        large_content = "x" * (MAX_SOURCE_SIZE + 1)
        source_path.write_text(large_content)

        with pytest.raises(ValueError, match="too large"):
            run_ingest(source_path, wiki_store)

    def test_ingest_file_at_max_size_accepted(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that files at exactly MAX_SOURCE_SIZE are accepted."""
        source_path = wiki_store.root / "raw" / "max-size.md"
        # Create a file exactly at MAX_SOURCE_SIZE
        content = "x" * MAX_SOURCE_SIZE
        source_path.write_text(content)

        # Mock LLM response
        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = '{"source_summary": "Summary", "pages": []}'

        # Should not raise
        summary, pages = run_ingest(source_path, wiki_store)
        assert summary == "Summary"

    def test_ingest_file_at_min_size_accepted(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that files at exactly MIN_SOURCE_SIZE are accepted."""
        source_path = wiki_store.root / "raw" / "min-size.md"
        # Create a file with exactly 1 byte
        source_path.write_text("x")

        # Mock LLM response
        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = '{"source_summary": "Summary", "pages": []}'

        # Should not raise
        summary, pages = run_ingest(source_path, wiki_store)
        assert summary == "Summary"

    def test_ingest_normal_file_accepted(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that normal-sized files are accepted."""
        source_path = wiki_store.root / "raw" / "normal.md"
        source_path.write_text("# Normal File\n\nThis is normal content.")

        # Mock LLM response
        mock_llm_client.chat.completions.create.return_value.choices[0].message.content = '{"source_summary": "Summary", "pages": []}'

        # Should not raise
        summary, pages = run_ingest(source_path, wiki_store)
        assert summary == "Summary"
