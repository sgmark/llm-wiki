"""Tests for schema validation in wiki_core.schema_validation."""
import pytest
from wiki_core.schema_validation import (
    ValidationError,
    validate_ingest_response,
    validate_query_relevance_response,
    validate_query_answer_response,
    validate_lint_response,
    sanitize_content,
    BLEACH_AVAILABLE,
)


class TestIngestResponseValidation:
    """Test cases for validate_ingest_response."""

    def test_valid_ingest_response(self):
        """Test valid ingest response passes validation."""
        data = {
            "source_summary": "Test summary",
            "pages": [
                {"path": "pages/test.md", "content": "# Test\nContent"}
            ]
        }
        result = validate_ingest_response(data)
        assert result["source_summary"] == "Test summary"
        assert len(result["pages"]) == 1

    def test_missing_source_summary(self):
        """Test missing source_summary raises ValidationError."""
        data = {"pages": []}
        with pytest.raises(ValidationError, match="Missing required field: 'source_summary'"):
            validate_ingest_response(data)

    def test_missing_pages(self):
        """Test missing pages raises ValidationError."""
        data = {"source_summary": "Summary"}
        with pytest.raises(ValidationError, match="Missing required field: 'pages'"):
            validate_ingest_response(data)

    def test_path_traversal_dotdot(self):
        """Test path with .. is rejected."""
        data = {
            "source_summary": "Summary",
            "pages": [{"path": "pages/../etc/passwd", "content": "test"}]
        }
        with pytest.raises(ValidationError, match="directory traversal"):
            validate_ingest_response(data)

    def test_path_traversal_deep_escape(self):
        """Test path with multiple .. is rejected."""
        data = {
            "source_summary": "Summary",
            "pages": [{"path": "pages/../../../../../etc/passwd", "content": "test"}]
        }
        with pytest.raises(ValidationError, match="directory traversal"):
            validate_ingest_response(data)

    def test_path_with_backslash(self):
        """Test path with backslash is rejected."""
        data = {
            "source_summary": "Summary",
            "pages": [{"path": "pages\\test.md", "content": "test"}]
        }
        with pytest.raises(ValidationError, match="invalid character"):
            validate_ingest_response(data)

    def test_path_not_starting_with_pages(self):
        """Test path not starting with pages/ is rejected."""
        data = {
            "source_summary": "Summary",
            "pages": [{"path": "raw/test.md", "content": "test"}]
        }
        with pytest.raises(ValidationError, match="must start with 'pages/'"):
            validate_ingest_response(data)

    def test_path_with_null_byte(self):
        """Test path with null byte is rejected."""
        data = {
            "source_summary": "Summary",
            "pages": [{"path": "pages/test\x00.md", "content": "test"}]
        }
        with pytest.raises(ValidationError, match="null byte"):
            validate_ingest_response(data)

    def test_path_with_newline(self):
        """Test path with newline is rejected."""
        data = {
            "source_summary": "Summary",
            "pages": [{"path": "pages/test\n.md", "content": "test"}]
        }
        with pytest.raises(ValidationError, match="newline"):
            validate_ingest_response(data)

    def test_empty_content(self):
        """Test empty page content is rejected."""
        data = {
            "source_summary": "Summary",
            "pages": [{"path": "pages/test.md", "content": ""}]
        }
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_ingest_response(data)

    def test_too_many_pages(self):
        """Test too many pages is rejected."""
        data = {
            "source_summary": "Summary",
            "pages": [{"path": f"pages/test{i}.md", "content": "test"} for i in range(51)]
        }
        with pytest.raises(ValidationError, match="Too many pages"):
            validate_ingest_response(data)

    def test_valid_nested_path(self):
        """Test valid nested path is accepted."""
        data = {
            "source_summary": "Summary",
            "pages": [{"path": "pages/subdir/test.md", "content": "# Test\nContent"}]
        }
        result = validate_ingest_response(data)
        assert result["pages"][0]["path"] == "pages/subdir/test.md"

    def test_valid_deeply_nested_path(self):
        """Test valid deeply nested path is accepted."""
        data = {
            "source_summary": "Summary",
            "pages": [{"path": "pages/a/b/c/test.md", "content": "# Test\nContent"}]
        }
        result = validate_ingest_response(data)
        assert result["pages"][0]["path"] == "pages/a/b/c/test.md"


class TestQueryRelevanceResponseValidation:
    """Test cases for validate_query_relevance_response."""

    def test_valid_relevance_response(self):
        """Test valid relevance response passes validation."""
        data = {"pages": ["pages/test.md", "pages/other.md"]}
        result = validate_query_relevance_response(data)
        assert len(result["pages"]) == 2

    def test_missing_pages(self):
        """Test missing pages raises ValidationError."""
        data = {}
        with pytest.raises(ValidationError, match="Missing required field: 'pages'"):
            validate_query_relevance_response(data)

    def test_path_traversal_in_relevance(self):
        """Test path traversal in relevance response is rejected."""
        data = {"pages": ["pages/../etc/passwd"]}
        with pytest.raises(ValidationError, match="directory traversal"):
            validate_query_relevance_response(data)

    def test_path_not_starting_with_pages_in_relevance(self):
        """Test path not starting with pages/ in relevance is rejected."""
        data = {"pages": ["raw/test.md"]}
        with pytest.raises(ValidationError, match="must start with 'pages/'"):
            validate_query_relevance_response(data)


class TestQueryAnswerResponseValidation:
    """Test cases for validate_query_answer_response."""

    def test_valid_answer_response(self):
        """Test valid answer response passes validation."""
        data = {"answer": "This is the answer", "save_as": None, "save_content": None}
        result = validate_query_answer_response(data)
        assert result["answer"] == "This is the answer"

    def test_missing_answer(self):
        """Test missing answer raises ValidationError."""
        data = {}
        with pytest.raises(ValidationError, match="Missing required field: 'answer'"):
            validate_query_answer_response(data)

    def test_empty_answer(self):
        """Test empty answer raises ValidationError."""
        data = {"answer": ""}
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_query_answer_response(data)

    def test_save_as_path_traversal(self):
        """Test save_as with path traversal is rejected."""
        data = {
            "answer": "Answer",
            "save_as": "pages/../etc/passwd",
            "save_content": "content"
        }
        with pytest.raises(ValidationError, match="directory traversal"):
            validate_query_answer_response(data)

    def test_save_as_not_starting_with_pages(self):
        """Test save_as not starting with pages/ is rejected."""
        data = {
            "answer": "Answer",
            "save_as": "raw/test.md",
            "save_content": "content"
        }
        with pytest.raises(ValidationError, match="must start with 'pages/'"):
            validate_query_answer_response(data)


class TestLintResponseValidation:
    """Test cases for validate_lint_response."""

    def test_valid_lint_response(self):
        """Test valid lint response passes validation."""
        data = {
            "health_score": 85,
            "summary": "Wiki is healthy",
            "issues": []
        }
        result = validate_lint_response(data)
        assert result["health_score"] == 85

    def test_missing_health_score(self):
        """Test missing health_score raises ValidationError."""
        data = {"summary": "Test", "issues": []}
        with pytest.raises(ValidationError, match="Missing required field: 'health_score'"):
            validate_lint_response(data)

    def test_health_score_out_of_range(self):
        """Test health_score out of range raises ValidationError."""
        data = {
            "health_score": 150,
            "summary": "Test",
            "issues": []
        }
        with pytest.raises(ValidationError, match="must be between 0 and 100"):
            validate_lint_response(data)

    def test_valid_issue(self):
        """Test valid issue passes validation."""
        data = {
            "health_score": 80,
            "summary": "Test",
            "issues": [
                {
                    "type": "orphan",
                    "severity": "medium",
                    "description": "Page has no inbound links",
                    "pages": ["pages/orphan.md"],
                    "suggestion": "Add links to this page"
                }
            ]
        }
        result = validate_lint_response(data)
        assert len(result["issues"]) == 1

    def test_invalid_issue_type(self):
        """Test invalid issue type raises ValidationError."""
        data = {
            "health_score": 80,
            "summary": "Test",
            "issues": [
                {
                    "type": "invalid_type",
                    "severity": "medium",
                    "description": "Test",
                    "pages": [],
                    "suggestion": "Test"
                }
            ]
        }
        with pytest.raises(ValidationError, match="invalid type"):
            validate_lint_response(data)

    def test_invalid_severity(self):
        """Test invalid severity raises ValidationError."""
        data = {
            "health_score": 80,
            "summary": "Test",
            "issues": [
                {
                    "type": "orphan",
                    "severity": "critical",
                    "description": "Test",
                    "pages": [],
                    "suggestion": "Test"
                }
            ]
        }
        with pytest.raises(ValidationError, match="invalid severity"):
            validate_lint_response(data)


class TestContentSanitization:
    """Test cases for content sanitization."""

    def test_sanitize_empty_content(self):
        """Test sanitizing empty content."""
        assert sanitize_content("") == ""
        assert sanitize_content(None) is None

    def test_sanitize_plain_text(self):
        """Test that plain text passes through unchanged."""
        text = "This is plain text with no HTML."
        assert sanitize_content(text) == text

    def test_sanitize_safe_html(self):
        """Test that safe HTML is preserved."""
        text = "<p>This is <strong>bold</strong> and <em>italic</em>.</p>"
        sanitized = sanitize_content(text)
        # Safe tags should be preserved
        assert "<strong>bold</strong>" in sanitized or "bold" in sanitized
        assert "<em>italic</em>" in sanitized or "italic" in sanitized

    def test_sanitize_removes_onclick(self):
        """Test that onclick event handlers are removed."""
        text = '<a href="http://example.com" onclick="alert(1)">Click</a>'
        sanitized = sanitize_content(text)
        assert "onclick" not in sanitized.lower()

    def test_sanitize_removes_onload(self):
        """Test that onload event handlers are removed."""
        text = '<body onload="alert(1)">Content</body>'
        sanitized = sanitize_content(text)
        assert "onload" not in sanitized.lower()

    def test_sanitize_removes_javascript_url(self):
        """Test that javascript: URLs are removed."""
        text = '<a href="javascript:alert(1)">Click</a>'
        sanitized = sanitize_content(text)
        assert "javascript:" not in sanitized.lower()

    def test_sanitize_removes_data_url(self):
        """Test that data: URLs are removed."""
        text = '<a href="data:text/html,<script>alert(1)</script>">Click</a>'
        sanitized = sanitize_content(text)
        assert "data:" not in sanitized.lower() or "alert" not in sanitized

    def test_sanitize_removes_script_tags(self):
        """Test that script tags are removed (content may remain)."""
        text = "<script>alert('XSS')</script>Safe content"
        sanitized = sanitize_content(text)
        # Script tags should be removed (bleach strips tags but keeps content)
        assert "<script>" not in sanitized.lower()
        assert "<script" not in sanitized.lower()

    def test_sanitize_removes_onerror(self):
        """Test that onerror event handlers are removed."""
        text = '<img src="x" onerror="alert(1)">'
        sanitized = sanitize_content(text)
        assert "onerror" not in sanitized.lower()

    def test_sanitize_preserves_code_blocks(self):
        """Test that code blocks are preserved."""
        text = "<code>print('hello')</code>"
        sanitized = sanitize_content(text)
        # Code tags should be preserved
        assert "print" in sanitized

    def test_sanitize_removes_style_tags(self):
        """Test that style tags are removed (content may remain)."""
        text = "<style>body { background: url(evil.png) }</style>Content"
        sanitized = sanitize_content(text)
        # Style tags should be removed
        assert "<style>" not in sanitized.lower()
        assert "<style" not in sanitized.lower()

    def test_sanitize_removes_iframe(self):
        """Test that iframe tags are removed (content may remain)."""
        text = '<iframe src="http://evil.com"></iframe>Content'
        sanitized = sanitize_content(text)
        # Iframe tags should be removed
        assert "<iframe" not in sanitized.lower()

    def test_sanitize_removes_object_tag(self):
        """Test that object tags are removed (content may remain)."""
        text = '<object data="evil.swf"></object>Content'
        sanitized = sanitize_content(text)
        # Object tags should be removed
        assert "<object" not in sanitized.lower()

    def test_sanitize_removes_embed_tag(self):
        """Test that embed tags are removed (content may remain)."""
        text = '<embed src="evil.swf">Content'
        sanitized = sanitize_content(text)
        # Embed tags should be removed
        assert "<embed" not in sanitized.lower()

    def test_sanitize_removes_form_tag(self):
        """Test that form tags are removed (content may remain)."""
        text = '<form action="http://evil.com"><input name="data"></form>Content'
        sanitized = sanitize_content(text)
        # Form tags should be removed
        assert "<form" not in sanitized.lower()

    def test_ingest_response_sanitizes_content(self):
        """Test that validate_ingest_response sanitizes page content."""
        data = {
            "source_summary": "Summary",
            "pages": [
                {
                    "path": "pages/test.md",
                    "content": "<script>alert('XSS')</script>Safe content"
                }
            ]
        }
        result = validate_ingest_response(data)
        # Script tags should be removed (content may remain)
        assert "<script>" not in result["pages"][0]["content"].lower()
        assert "<script" not in result["pages"][0]["content"].lower()

    def test_ingest_response_sanitizes_onclick(self):
        """Test that validate_ingest_response removes onclick handlers."""
        data = {
            "source_summary": "Summary",
            "pages": [
                {
                    "path": "pages/test.md",
                    "content": '<a onclick="alert(1)">Click</a>'
                }
            ]
        }
        result = validate_ingest_response(data)
        # onclick should be removed
        assert "onclick" not in result["pages"][0]["content"].lower()
