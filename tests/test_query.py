"""Tests for the query flow in wiki_core.query."""
from unittest.mock import MagicMock

import pytest
from wiki_core.query import run_query
from wiki_core.store import WikiStore
from tests.conftest import create_mock_response


class TestRunQuery:
    """Test cases for run_query function."""

    def test_query_returns_answer(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that query returns an answer."""
        wiki_store.write_page("pages/test.md", "# Test\nTest content")
        wiki_store.rebuild_index()

        # Mock responses
        mock_llm_client.chat.completions.create.side_effect = [
            create_mock_response('{"pages": ["pages/test.md"]}'),
            create_mock_response('{"answer": "This is the answer", "save_as": null, "save_content": null}'),
        ]

        answer, saved_path = run_query("What is test?", wiki_store)

        assert answer == "This is the answer"
        assert saved_path is None

    def test_query_logs_event(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that query logs the event."""
        wiki_store.write_page("pages/test.md", "# Test\nContent")
        wiki_store.rebuild_index()

        mock_llm_client.chat.completions.create.side_effect = [
            create_mock_response('{"pages": []}'),
            create_mock_response('{"answer": "No info", "save_as": null, "save_content": null}'),
        ]

        run_query("Test question", wiki_store)

        log_content = wiki_store.log_path.read_text()
        assert "query" in log_content
        assert "Test question" in log_content

    def test_query_with_save_creates_page(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that query with save=True creates a new page."""
        wiki_store.write_page("pages/existing.md", "# Existing\nContent")
        wiki_store.rebuild_index()

        mock_llm_client.chat.completions.create.side_effect = [
            # Relevance
            create_mock_response('{"pages": ["pages/existing.md"]}'),
            # Answer with save
            create_mock_response('{"answer": "The answer", "save_as": "pages/answer-page.md", "save_content": "# Answer Page\\n\\nSaved content"}'),
        ]

        answer, saved_path = run_query("Save this?", wiki_store, save=True)

        assert saved_path == "pages/answer-page.md"
        assert (wiki_store.root / "pages/answer-page.md").exists()

    def test_query_with_save_rebuilds_index(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that query with save rebuilds the index."""
        wiki_store.write_page("pages/existing.md", "# Existing\nContent")
        wiki_store.rebuild_index()

        mock_llm_client.chat.completions.create.side_effect = [
            create_mock_response('{"pages": []}'),
            create_mock_response('{"answer": "Answer", "save_as": "pages/saved.md", "save_content": "# Saved\\n\\nContent"}'),
        ]

        run_query("Save me", wiki_store, save=True)

        index = wiki_store.read_index()
        assert "saved" in index.lower() or "Saved" in index

    def test_query_no_relevant_pages(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test query when no relevant pages are found."""
        mock_llm_client.chat.completions.create.side_effect = [
            create_mock_response('{"pages": []}'),
            create_mock_response('{"answer": "No relevant pages found", "save_as": null, "save_content": null}'),
        ]

        answer, saved_path = run_query("Unknown topic", wiki_store)

        assert "No relevant pages found" in answer
        assert saved_path is None

    def test_query_invalid_relevance_json(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test query when relevance response is invalid JSON."""
        wiki_store.write_page("pages/test.md", "# Test\nContent")
        wiki_store.rebuild_index()

        mock_llm_client.chat.completions.create.side_effect = [
            create_mock_response("Not valid JSON"),  # Relevance
            create_mock_response('{"answer": "Fallback answer", "save_as": null, "save_content": null}'),  # Answer
        ]

        answer, saved_path = run_query("Test", wiki_store)

        assert answer == "Fallback answer"

    def test_query_invalid_answer_json(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test query when answer response is invalid JSON."""
        wiki_store.write_page("pages/test.md", "# Test\nContent")
        wiki_store.rebuild_index()

        mock_llm_client.chat.completions.create.side_effect = [
            create_mock_response('{"pages": ["pages/test.md"]}'),
            create_mock_response("Just plain text answer"),  # Invalid JSON
        ]

        answer, saved_path = run_query("Test", wiki_store)

        assert answer == "Just plain text answer"
        assert saved_path is None

    def test_query_with_multiple_relevant_pages(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test query with multiple relevant pages."""
        wiki_store.write_page("pages/page1.md", "# Page 1\nContent 1")
        wiki_store.write_page("pages/page2.md", "# Page 2\nContent 2")
        wiki_store.write_page("pages/page3.md", "# Page 3\nContent 3")
        wiki_store.rebuild_index()

        mock_llm_client.chat.completions.create.side_effect = [
            create_mock_response('{"pages": ["pages/page1.md", "pages/page2.md", "pages/page3.md"]}'),
            create_mock_response('{"answer": "Combined answer", "save_as": null, "save_content": null}'),
        ]

        answer, saved_path = run_query("Multi page query", wiki_store)

        assert answer == "Combined answer"

    def test_query_save_without_save_flag(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that save content is not created when save=False."""
        wiki_store.write_page("pages/test.md", "# Test\nContent")
        wiki_store.rebuild_index()

        mock_llm_client.chat.completions.create.side_effect = [
            create_mock_response('{"pages": ["pages/test.md"]}'),
            create_mock_response('{"answer": "Answer", "save_as": "pages/should-not-save.md", "save_content": "Content"}'),
        ]

        answer, saved_path = run_query("Test", wiki_store, save=False)

        assert saved_path is None
        assert not (wiki_store.root / "pages/should-not-save.md").exists()

    def test_query_with_schema_in_prompt(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that schema is included in the system prompt."""
        wiki_store.write_page("pages/test.md", "# Test\nContent")
        wiki_store.rebuild_index()

        mock_llm_client.chat.completions.create.side_effect = [
            create_mock_response('{"pages": []}'),
            create_mock_response('{"answer": "Answer", "save_as": null, "save_content": null}'),
        ]

        run_query("Test", wiki_store)

        # Check second call (answer) includes schema
        call_args = mock_llm_client.chat.completions.create.call_args_list[1]
        messages = call_args[1]["messages"]
        system_msg = messages[0]["content"]
        assert "schema" in system_msg.lower() or "convention" in system_msg.lower()

    def test_query_empty_wiki(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test query on empty wiki."""
        mock_llm_client.chat.completions.create.side_effect = [
            create_mock_response('{"pages": []}'),
            create_mock_response('{"answer": "No information available", "save_as": null, "save_content": null}'),
        ]

        answer, saved_path = run_query("Anything?", wiki_store)

        assert "No information available" in answer
        assert saved_path is None

    def test_query_save_flag_true_but_no_save_as(
        self, wiki_store: WikiStore, mock_llm_client
    ):
        """Test that save=True with no save_as in response doesn't create page."""
        wiki_store.write_page("pages/test.md", "# Test\nContent")
        wiki_store.rebuild_index()

        mock_llm_client.chat.completions.create.side_effect = [
            create_mock_response('{"pages": ["pages/test.md"]}'),
            create_mock_response('{"answer": "Answer only", "save_as": null, "save_content": null}'),
        ]

        answer, saved_path = run_query("Test", wiki_store, save=True)

        assert saved_path is None
        assert answer == "Answer only"
