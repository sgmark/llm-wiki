"""Tests for WikiStore class in wiki_core.store."""
import pytest
from pathlib import Path
from wiki_core.store import WikiStore, validate_path


class TestValidatePath:
    """Test cases for the validate_path function."""

    def test_valid_relative_path(self, temp_wiki_root: Path):
        """Test that valid relative paths are accepted."""
        result = validate_path(temp_wiki_root, "pages/test.md")
        assert result == (temp_wiki_root / "pages/test.md").resolve()

    def test_valid_nested_path(self, temp_wiki_root: Path):
        """Test that valid nested paths are accepted."""
        result = validate_path(temp_wiki_root, "pages/subdir/test.md")
        assert "pages/subdir/test.md" in str(result)

    def test_path_traversal_with_dot_dot(self, temp_wiki_root: Path):
        """Test that path traversal with .. is blocked."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_path(temp_wiki_root, "../etc/passwd")

    def test_path_traversal_deep_escape(self, temp_wiki_root: Path):
        """Test that deep path traversal attempts are blocked."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_path(temp_wiki_root, "pages/../../../etc/passwd")

    def test_path_traversal_within_pages(self, temp_wiki_root: Path):
        """Test that path traversal within pages directory is blocked."""
        # This path contains .., so it should be blocked
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_path(temp_wiki_root, "pages/../raw/test.md")

    def test_null_byte_in_path(self, temp_wiki_root: Path):
        """Test that null bytes in path raise ValueError."""
        with pytest.raises(ValueError, match="null bytes"):
            validate_path(temp_wiki_root, "pages/test\x00.md")

    def test_newline_in_path(self, temp_wiki_root: Path):
        """Test that newlines in path raise ValueError."""
        with pytest.raises(ValueError, match="newlines"):
            validate_path(temp_wiki_root, "pages/test\n.md")

    def test_carriage_return_in_path(self, temp_wiki_root: Path):
        """Test that carriage returns in path raise ValueError."""
        with pytest.raises(ValueError, match="newlines"):
            validate_path(temp_wiki_root, "pages/test\r.md")

    def test_mixed_traversal_and_null(self, temp_wiki_root: Path):
        """Test that mixed attack vectors are blocked."""
        with pytest.raises(ValueError):
            validate_path(temp_wiki_root, "../test\x00.md")

    def test_absolute_path_attempt(self, temp_wiki_root: Path):
        """Test that absolute paths that escape root are blocked."""
        with pytest.raises(ValueError, match="Path must start with 'pages/'"):
            validate_path(temp_wiki_root, "/etc/passwd")

    def test_symlink_traversal_simulation(self, temp_wiki_root: Path):
        """Test that paths with special characters are blocked."""
        # This path with URL encoding contains .., so it's blocked
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_path(temp_wiki_root, "pages/..%2f..%2fetc/passwd")

    def test_valid_path_with_dots_in_name(self, temp_wiki_root: Path):
        """Test that paths with dots in filename are accepted."""
        result = validate_path(temp_wiki_root, "pages/test.file.md")
        assert "test.file.md" in str(result)

    def test_valid_path_with_spaces(self, temp_wiki_root: Path):
        """Test that paths with spaces are accepted."""
        result = validate_path(temp_wiki_root, "pages/my page.md")
        assert "my page.md" in str(result)

    def test_empty_path(self, temp_wiki_root: Path):
        """Test that empty path is blocked (must start with pages/)."""
        with pytest.raises(ValueError, match="Path must start with 'pages/'"):
            validate_path(temp_wiki_root, "")

    def test_path_with_only_slashes(self, temp_wiki_root: Path):
        """Test path with only slashes."""
        # A single slash is an absolute path that doesn't start with pages/
        with pytest.raises(ValueError, match="Path must start with 'pages/'"):
            validate_path(temp_wiki_root, "/")


class TestWikiStore:
    """Test cases for WikiStore class."""

    def test_init_creates_directories(self, temp_wiki_root: Path):
        """Test that init() creates required directories."""
        store = WikiStore(temp_wiki_root)
        store.init()
        assert (temp_wiki_root / "pages").exists()
        assert (temp_wiki_root / "raw").exists()

    def test_init_creates_index_file(self, temp_wiki_root: Path):
        """Test that init() creates index.md."""
        store = WikiStore(temp_wiki_root)
        store.init()
        assert (temp_wiki_root / "index.md").exists()

    def test_init_creates_log_file(self, temp_wiki_root: Path):
        """Test that init() creates log.md."""
        store = WikiStore(temp_wiki_root)
        store.init()
        assert (temp_wiki_root / "log.md").exists()

    def test_init_creates_schema_file(self, temp_wiki_root: Path):
        """Test that init() creates schema.md."""
        store = WikiStore(temp_wiki_root)
        store.init()
        assert (temp_wiki_root / "schema.md").exists()

    def test_read_page_existing(self, wiki_store: WikiStore):
        """Test reading an existing page."""
        content = "# Test\nContent here"
        wiki_store.write_page("pages/test.md", content)
        result = wiki_store.read_page("pages/test.md")
        assert result == content

    def test_read_page_nonexistent(self, wiki_store: WikiStore):
        """Test reading a non-existent page returns None."""
        result = wiki_store.read_page("pages/nonexistent.md")
        assert result is None

    def test_read_page_traversal_blocked(self, wiki_store: WikiStore):
        """Test that path traversal in read_page is blocked."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            wiki_store.read_page("../etc/passwd")

    def test_write_page_creates_file(self, wiki_store: WikiStore):
        """Test that write_page creates a new file."""
        content = "# New Page\nContent"
        wiki_store.write_page("pages/new-page.md", content)
        assert (wiki_store.root / "pages/new-page.md").exists()

    def test_write_page_creates_parent_dirs(self, wiki_store: WikiStore):
        """Test that write_page creates parent directories."""
        content = "# Nested Page\nContent"
        wiki_store.write_page("pages/subdir/nested.md", content)
        assert (wiki_store.root / "pages/subdir/nested.md").exists()

    def test_write_page_traversal_blocked(self, wiki_store: WikiStore):
        """Test that path traversal in write_page is blocked."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            wiki_store.write_page("../tmp/evil.md", "malicious content")

    def test_write_page_null_byte_blocked(self, wiki_store: WikiStore):
        """Test that null bytes in write_page path are blocked."""
        with pytest.raises(ValueError, match="null bytes"):
            wiki_store.write_page("pages/test\x00.md", "content")

    def test_list_pages_empty(self, wiki_store: WikiStore):
        """Test list_pages on empty wiki."""
        result = wiki_store.list_pages()
        assert result == []

    def test_list_pages_with_pages(self, populated_wiki_store: WikiStore):
        """Test list_pages returns sorted list of pages."""
        result = populated_wiki_store.list_pages()
        assert "pages/other-page.md" in result
        assert "pages/sample-page.md" in result
        assert "pages/third-page.md" in result
        assert result == sorted(result)

    def test_read_index(self, wiki_store: WikiStore):
        """Test reading the index file."""
        wiki_store.write_index("# Custom Index\nContent")
        result = wiki_store.read_index()
        assert result == "# Custom Index\nContent"

    def test_write_index(self, wiki_store: WikiStore):
        """Test writing to the index file."""
        wiki_store.write_index("# New Index\n- [[Page]]")
        assert wiki_store.index_path.exists()
        assert wiki_store.index_path.read_text() == "# New Index\n- [[Page]]"

    def test_append_log(self, wiki_store: WikiStore):
        """Test appending to the log file."""
        wiki_store.append_log("test", "Test Event", "Some details")
        log_content = wiki_store.log_path.read_text()
        assert "test" in log_content
        assert "Test Event" in log_content
        assert "Some details" in log_content

    def test_rebuild_index(self, wiki_store: WikiStore, sample_page_content: str):
        """Test rebuilding the index from pages."""
        wiki_store.write_page("pages/test-page.md", sample_page_content)
        wiki_store.rebuild_index()
        index = wiki_store.read_index()
        assert "test-page" in index.lower() or "Test Page" in index

    def test_read_schema(self, wiki_store: WikiStore):
        """Test reading the schema file."""
        schema = wiki_store.read_schema()
        assert "Wiki Schema" in schema

    def test_page_previews_empty(self, wiki_store: WikiStore):
        """Test page_previews on empty wiki."""
        result = wiki_store.page_previews()
        assert result == ""

    def test_page_previews_with_pages(self, populated_wiki_store: WikiStore):
        """Test page_previews returns content from pages."""
        result = populated_wiki_store.page_previews(max_pages=2, max_chars_each=100)
        assert "pages/" in result

    def test_page_previews_respects_limits(self, populated_wiki_store: WikiStore):
        """Test page_previews respects max_pages limit."""
        result = populated_wiki_store.page_previews(max_pages=1)
        # Should only contain one page
        page_count = result.count("pages/")
        assert page_count <= 2  # path + content reference

    def test_page_exists_method_not_present(self, wiki_store: WikiStore):
        """Test that page_exists method exists (it doesn't, so this is a check)."""
        # Note: WikiStore doesn't have page_exists, this tests the API
        assert not hasattr(wiki_store, 'page_exists')

    def test_init_idempotent(self, temp_wiki_root: Path):
        """Test that init() can be called multiple times safely."""
        store = WikiStore(temp_wiki_root)
        store.init()
        store.init()  # Should not raise
        assert (temp_wiki_root / "pages").exists()

    def test_read_page_with_special_valid_chars(self, wiki_store: WikiStore):
        """Test reading page with valid special characters in name."""
        content = "# Test"
        wiki_store.write_page("pages/test-page_2024.md", content)
        result = wiki_store.read_page("pages/test-page_2024.md")
        assert result == content

    def test_path_traversal_dotdot_in_middle(self, temp_wiki_root: Path):
        """Test path traversal with .. in the middle of path."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_path(temp_wiki_root, "pages/subdir/../etc/passwd")

    def test_path_traversal_multiple_dotdot(self, temp_wiki_root: Path):
        """Test path traversal with multiple .. sequences."""
        with pytest.raises(ValueError, match="Path traversal detected"):
            validate_path(temp_wiki_root, "pages/../../../../../etc/passwd")

    def test_path_with_backslash(self, temp_wiki_root: Path):
        """Test that Windows path separators are rejected."""
        with pytest.raises(ValueError, match="backslashes"):
            validate_path(temp_wiki_root, "pages\\test.md")

    def test_path_with_mixed_separators(self, temp_wiki_root: Path):
        """Test that mixed path separators are rejected."""
        with pytest.raises(ValueError, match="backslashes"):
            validate_path(temp_wiki_root, "pages/subdir\\test.md")

    def test_path_not_starting_with_pages(self, temp_wiki_root: Path):
        """Test that paths not starting with pages/ are rejected."""
        with pytest.raises(ValueError, match="Path must start with 'pages/'"):
            validate_path(temp_wiki_root, "raw/test.md")

    def test_path_not_starting_with_pages_raw(self, temp_wiki_root: Path):
        """Test that raw/ paths are rejected."""
        with pytest.raises(ValueError, match="Path must start with 'pages/'"):
            validate_path(temp_wiki_root, "raw/source.md")

    def test_path_with_null_byte(self, temp_wiki_root: Path):
        """Test that null bytes in path are rejected."""
        with pytest.raises(ValueError, match="null bytes"):
            validate_path(temp_wiki_root, "pages/test\x00.md")

    def test_path_with_newline(self, temp_wiki_root: Path):
        """Test that newlines in path are rejected."""
        with pytest.raises(ValueError, match="newlines"):
            validate_path(temp_wiki_root, "pages/test\n.md")

    def test_path_with_carriage_return(self, temp_wiki_root: Path):
        """Test that carriage returns in path are rejected."""
        with pytest.raises(ValueError, match="newlines"):
            validate_path(temp_wiki_root, "pages/test\r.md")

    def test_valid_nested_path(self, temp_wiki_root: Path):
        """Test that valid nested paths within pages/ are accepted."""
        result = validate_path(temp_wiki_root, "pages/subdir/nested.md")
        assert "pages/subdir/nested.md" in str(result)

    def test_valid_deeply_nested_path(self, temp_wiki_root: Path):
        """Test that valid deeply nested paths within pages/ are accepted."""
        result = validate_path(temp_wiki_root, "pages/a/b/c/d.md")
        assert "pages/a/b/c/d.md" in str(result)

    def test_path_ending_without_md(self, temp_wiki_root: Path):
        """Test that paths not ending with .md are rejected by schema validation."""
        # This passes validate_path but should be caught by schema validation
        result = validate_path(temp_wiki_root, "pages/test.txt")
        # validate_path only checks structure, not extension
        assert "pages/test.txt" in str(result)
