"""Tests for linting functions in wiki_core.lint."""
import re
from unittest.mock import MagicMock

import pytest
from wiki_core.lint import (
    _extract_title,
    _structural_lint,
    fix_issues,
    run_lint,
    WIKILINK_RE,
)
from wiki_core.store import WikiStore
from tests.conftest import create_mock_response


class TestExtractTitle:
    """Test cases for _extract_title function."""

    def test_extract_title_from_header(self):
        """Test extracting title from markdown header."""
        content = "# My Page Title\nSome content"
        assert _extract_title(content) == "My Page Title"

    def test_extract_title_with_extra_spaces(self):
        """Test extracting title with extra whitespace."""
        content = "#   Spaced Title   \nContent"
        assert _extract_title(content) == "Spaced Title"

    def test_no_title_returns_none(self):
        """Test that content without header returns None."""
        content = "Just some content without a title"
        assert _extract_title(content) is None

    def test_empty_string_returns_none(self):
        """Test that empty string returns None."""
        assert _extract_title("") is None

    def test_only_header(self):
        """Test content with only a header."""
        content = "# Only Header"
        assert _extract_title(content) == "Only Header"

    def test_frontmatter_before_title(self):
        """Test extracting title when frontmatter is present."""
        content = """---
tags: [test]
---

# Page with Frontmatter

Content here."""
        assert _extract_title(content) == "Page with Frontmatter"

    def test_multiple_headers_returns_first(self):
        """Test that only the first H1 is returned as title."""
        content = "# First Title\n\n## Second\n\n# Third"
        assert _extract_title(content) == "First Title"

    def test_h2_not_title(self):
        """Test that H2 headers are not extracted as title."""
        content = "## Section Header\nContent"
        assert _extract_title(content) is None


class TestWikilinkRegex:
    """Test cases for WIKILINK_RE pattern."""

    def test_single_wikilink(self):
        """Test extracting single wikilink."""
        text = "This is a [[Page Title]] link"
        assert WIKILINK_RE.findall(text) == ["Page Title"]

    def test_multiple_wikilinks(self):
        """Test extracting multiple wikilinks."""
        text = "[[First]] and [[Second]] and [[Third]]"
        assert WIKILINK_RE.findall(text) == ["First", "Second", "Third"]

    def test_wikilink_with_special_chars(self):
        """Test wikilinks with special characters."""
        text = "[[Page with Spaces]] and [[Page-with-dashes]]"
        assert WIKILINK_RE.findall(text) == ["Page with Spaces", "Page-with-dashes"]

    def test_no_wikilinks(self):
        """Test text without wikilinks."""
        text = "Just plain text"
        assert WIKILINK_RE.findall(text) == []

    def test_empty_string(self):
        """Test empty string."""
        assert WIKILINK_RE.findall("") == []

    def test_wikilink_in_list(self):
        """Test wikilinks in list items."""
        text = "- [[Item One]]\n- [[Item Two]]"
        assert WIKILINK_RE.findall(text) == ["Item One", "Item Two"]

    def test_nested_brackets_not_wikilink(self):
        """Test that nested brackets are not wikilinks."""
        text = "[[Page]] with [not a link]"
        assert WIKILINK_RE.findall(text) == ["Page"]


class TestStructuralLint:
    """Test cases for _structural_lint function."""

    def test_no_orphans(self, wiki_store: WikiStore):
        """Test wiki with no orphan pages."""
        # Create pages that all link to each other
        wiki_store.write_page("pages/a.md", "# A\nRelated:\n- [[B]]")
        wiki_store.write_page("pages/b.md", "# B\nRelated:\n- [[A]]")
        issues = _structural_lint(wiki_store)
        orphan_issues = [i for i in issues if i["type"] == "orphan"]
        assert len(orphan_issues) == 0

    def test_orphan_pages(self, wiki_store: WikiStore):
        """Test detection of orphan pages (no inbound links)."""
        wiki_store.write_page("pages/linked.md", "# Linked\nRelated:\n- [[Orphan]]")
        wiki_store.write_page("pages/orphan.md", "# Orphan\nNo links here")
        issues = _structural_lint(wiki_store)
        orphan_issues = [i for i in issues if i["type"] == "orphan"]
        assert len(orphan_issues) == 1
        assert "pages/linked.md" in orphan_issues[0]["pages"]  # linked.md has no inbound

    def test_self_reference(self, wiki_store: WikiStore):
        """Test detection of self-references."""
        wiki_store.write_page("pages/self.md", "# Self\nRelated:\n- [[Self]]")
        issues = _structural_lint(wiki_store)
        self_ref_issues = [i for i in issues if i["type"] == "self_ref"]
        assert len(self_ref_issues) == 1
        assert "pages/self.md" in self_ref_issues[0]["pages"]

    def test_no_self_reference(self, wiki_store: WikiStore):
        """Test wiki with no self-references."""
        wiki_store.write_page("pages/a.md", "# A\nRelated:\n- [[B]]")
        wiki_store.write_page("pages/b.md", "# B\nRelated:\n- [[A]]")
        issues = _structural_lint(wiki_store)
        self_ref_issues = [i for i in issues if i["type"] == "self_ref"]
        assert len(self_ref_issues) == 0

    def test_broken_link(self, wiki_store: WikiStore):
        """Test detection of broken links (missing pages)."""
        wiki_store.write_page("pages/existing.md", "# Existing\nRelated:\n- [[Missing Page]]")
        issues = _structural_lint(wiki_store)
        broken_issues = [i for i in issues if i["type"] == "missing_page"]
        assert len(broken_issues) == 1
        assert broken_issues[0]["_missing_title"] == "Missing Page"

    def test_no_broken_links(self, wiki_store: WikiStore):
        """Test wiki with no broken links."""
        wiki_store.write_page("pages/a.md", "# A\nRelated:\n- [[B]]")
        wiki_store.write_page("pages/b.md", "# B\nRelated:\n- [[A]]")
        issues = _structural_lint(wiki_store)
        broken_issues = [i for i in issues if i["type"] == "missing_page"]
        assert len(broken_issues) == 0

    def test_empty_wiki(self, wiki_store: WikiStore):
        """Test linting an empty wiki."""
        issues = _structural_lint(wiki_store)
        assert issues == []

    def test_multiple_broken_links(self, wiki_store: WikiStore):
        """Test detection of multiple broken links."""
        wiki_store.write_page("pages/a.md", "# A\nLinks: [[Missing1]] [[Missing2]]")
        wiki_store.write_page("pages/b.md", "# B\nLinks: [[Missing1]] [[Missing3]]")
        issues = _structural_lint(wiki_store)
        broken_issues = [i for i in issues if i["type"] == "missing_page"]
        # Should have 3 missing page issues
        missing_titles = {i["_missing_title"] for i in broken_issues}
        assert missing_titles == {"Missing1", "Missing2", "Missing3"}

    def test_case_sensitive_titles(self, wiki_store: WikiStore):
        """Test that page titles are case-sensitive."""
        wiki_store.write_page("pages/page.md", "# Page\nRelated: [[page]]")
        issues = _structural_lint(wiki_store)
        broken = [i for i in issues if i["type"] == "missing_page"]
        # "page" != "Page", so this should be a broken link
        assert any(i["_missing_title"] == "page" for i in broken)

    def test_single_page_no_links(self, wiki_store: WikiStore):
        """Test single page with no links."""
        wiki_store.write_page("pages/alone.md", "# Alone\nNo links")
        issues = _structural_lint(wiki_store)
        orphan_issues = [i for i in issues if i["type"] == "orphan"]
        assert len(orphan_issues) == 1
        assert "pages/alone.md" in orphan_issues[0]["pages"]


class TestFixIssues:
    """Test cases for fix_issues function."""

    def test_fix_self_refs(self, wiki_store: WikiStore, mock_llm_client):
        """Test fixing self-references."""
        wiki_store.write_page("pages/self.md", "# Self\nRelated:\n- [[Self]]")
        issues = _structural_lint(wiki_store)
        report = fix_issues(issues, wiki_store)
        # Self-refs should be fixed programmatically
        content = wiki_store.read_page("pages/self.md")
        assert "[[Self]]" not in content

    def test_fix_issues_with_mock(self, wiki_store: WikiStore, mock_llm_client):
        """Test fix_issues with mocked LLM client."""
        wiki_store.write_page("pages/test.md", "# Test\nContent")
        # Create a proper issue dict with all required fields
        issues = [{"type": "self_ref", "pages": ["pages/test.md"], "description": "test", "severity": "low", "suggestion": "test"}]
        report = fix_issues(issues, wiki_store)
        assert "fixed" in report
        assert "skipped" in report


class TestRunLint:
    """Test cases for run_lint function."""

    def test_run_lint_empty_wiki(self, wiki_store: WikiStore, mock_llm_client):
        """Test running lint on empty wiki."""
        mock_llm_client.chat.completions.create.return_value = create_mock_response(
            '{"health_score": 100, "summary": "No pages", "issues": []}'
        )
        result = run_lint(wiki_store)
        assert result["health_score"] == 100
        assert result["issues"] == []

    def test_run_lint_with_issues(self, wiki_store: WikiStore, mock_llm_client):
        """Test running lint on wiki with issues."""
        wiki_store.write_page("pages/orphan.md", "# Orphan\nNo links")
        mock_llm_client.chat.completions.create.return_value = create_mock_response(
            '{"health_score": 80, "summary": "Test", "issues": []}'
        )
        result = run_lint(wiki_store)
        assert "issues" in result
        # Should have structural issues
        assert len(result["issues"]) >= 1

    def test_run_lint_logs_event(self, wiki_store: WikiStore, mock_llm_client):
        """Test that lint run is logged."""
        wiki_store.write_page("pages/test.md", "# Test\nContent")
        mock_llm_client.chat.completions.create.return_value = create_mock_response(
            '{"health_score": 90, "summary": "Good", "issues": []}'
        )
        run_lint(wiki_store)
        log_content = wiki_store.log_path.read_text()
        assert "lint" in log_content
        assert "health check" in log_content
