"""LLM output schema validation for the wiki project."""
import re
from typing import Any

from typing_extensions import TypedDict

# Try to import bleach for HTML sanitization
try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False


# Maximum allowed values for validation
MAX_PAGE_CONTENT_SIZE = 100 * 1024  # 100KB
MAX_PAGES_PER_RESPONSE = 50
# Strict pattern: must start with pages/, no .., no backslashes, ends with .md
# Allows: pages/name.md, pages/subdir/name.md
# Rejects: pages/../etc/passwd, pages/name..md, pages\name.md
PAGE_PATH_PATTERN = re.compile(r"^pages/[^\\/]+(/[^\\/]+)*\.md$")

# Additional patterns for security checks
PATH_TRAVERSAL_PATTERN = re.compile(r"\.\.|")

# Allowed HTML tags for wiki content (safe markdown/HTML subset)
ALLOWED_TAGS = [
    # Basic text formatting
    "p", "br", "strong", "em", "u", "s", "strike", "del",
    # Code and preformatted text
    "code", "pre", "kbd", "samp", "var",
    # Lists
    "ul", "ol", "li",
    # Links and images
    "a", "img",
    # Headings
    "h1", "h2", "h3", "h4", "h5", "h6",
    # Tables
    "table", "thead", "tbody", "tr", "th", "td",
    # Block elements
    "blockquote", "hr", "div", "span",
    # Wiki-specific
    "sup", "sub",
]

# Allowed attributes for HTML tags
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "th": ["scope"],
    "td": ["headers"],
}

# Attributes to strip (event handlers and dangerous attributes)
STRIPPED_ATTRIBUTES = [
    # Event handlers
    "onclick", "ondblclick", "onmousedown", "onmouseup", "onmouseover",
    "onmousemove", "onmouseout", "onmouseenter", "onmouseleave",
    "onkeydown", "onkeypress", "onkeyup", "onfocus", "onblur",
    "onchange", "onsubmit", "onreset", "onselect", "oninput",
    "onload", "onerror", "onabort", "onresize", "onscroll",
    "oncopy", "oncut", "onpaste", "ondrag", "ondragend", "ondragenter",
    "ondragleave", "ondragover", "ondragstart", "ondrop", "onwheel",
    # All on* attributes
    "on",
]

# Protocols to strip from URLs
STRIPPED_PROTOCOLS = ["javascript", "data", "vbscript"]


class ValidationError(Exception):
    """Exception raised when LLM output validation fails."""
    pass


# TypedDict schemas for expected LLM responses

class IngestPage(TypedDict):
    """Schema for a single page in ingest response."""
    path: str
    content: str


class IngestResponse(TypedDict):
    """Schema for LLM ingest response."""
    source_summary: str
    pages: list[IngestPage]


class QueryRelevanceResponse(TypedDict):
    """Schema for LLM relevance query response."""
    pages: list[str]


class QueryAnswerResponse(TypedDict):
    """Schema for LLM answer response."""
    answer: str
    save_as: str | None
    save_content: str | None


class LintIssue(TypedDict):
    """Schema for a single lint issue."""
    type: str
    severity: str
    description: str
    pages: list[str]
    suggestion: str


class LintResponse(TypedDict):
    """Schema for LLM lint response."""
    health_score: int
    summary: str
    issues: list[LintIssue]


# Validation functions

def _is_safe_path(path: str) -> tuple[bool, str]:
    """Check if a path is safe (no traversal attacks, no invalid characters).
    
    Args:
        path: The path to validate
        
    Returns:
        Tuple of (is_safe, error_message)
    """
    # Check for path traversal sequences
    if ".." in path:
        return False, "Path contains directory traversal sequence '..'"
    
    # Check for Windows path separators
    if "\\" in path:
        return False, "Path contains invalid character '\\'"
    
    # Check for null bytes
    if "\x00" in path:
        return False, "Path contains null byte"
    
    # Check for newlines
    if "\n" in path or "\r" in path:
        return False, "Path contains newline character"
    
    # Must start with pages/
    if not path.startswith("pages/"):
        return False, "Path must start with 'pages/'"
    
    # Must end with .md
    if not path.endswith(".md"):
        return False, "Path must end with '.md'"
    
    # Check for any other suspicious patterns
    if PAGE_PATH_PATTERN.match(path):
        return True, ""
    
    return False, f"Path has invalid format: {path}"


def sanitize_content(content: str) -> str:
    """Sanitize HTML/Markdown content to remove dangerous elements.
    
    This function removes potentially harmful HTML and JavaScript from content
    while preserving safe markdown and HTML formatting.
    
    Args:
        content: The content to sanitize
        
    Returns:
        Sanitized content with dangerous elements removed
    """
    if not content:
        return content
    
    # If bleach is available, use it for robust sanitization
    if BLEACH_AVAILABLE:
        # bleach.clean() handles most sanitization
        sanitized = bleach.clean(
            content,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            protocols=[],  # Empty protocols list blocks javascript:, data:, etc.
            strip=True,
            strip_comments=True,
        )
        return sanitized
    
    # Fallback: basic regex-based sanitization if bleach is not available
    # This is less robust but provides some protection
    
    # Remove script tags and their content
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<script[^>]*>', '', content, flags=re.IGNORECASE)
    content = re.sub(r'</script>', '', content, flags=re.IGNORECASE)
    
    # Remove style tags and their content
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.IGNORECASE | re.DOTALL)
    content = re.sub(r'<style[^>]*>', '', content, flags=re.IGNORECASE)
    content = re.sub(r'</style>', '', content, flags=re.IGNORECASE)
    
    # Remove iframe, object, embed, form tags and their content
    for tag in ['iframe', 'object', 'embed', 'form']:
        content = re.sub(r'<' + tag + r'[^>]*>.*?</' + tag + r'>', '', content, flags=re.IGNORECASE | re.DOTALL)
        content = re.sub(r'<' + tag + r'[^>]*>', '', content, flags=re.IGNORECASE)
        content = re.sub(r'</' + tag + r'>', '', content, flags=re.IGNORECASE)
    
    # Remove event handlers (onclick, onload, etc.)
    content = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', '', content, flags=re.IGNORECASE)
    content = re.sub(r'\s+on\w+\s*=\s*[^\s>]+', '', content, flags=re.IGNORECASE)
    
    # Remove javascript: URLs
    content = re.sub(r'href\s*=\s*["\']\s*javascript:[^"\']*["\']', 'href="#"', content, flags=re.IGNORECASE)
    content = re.sub(r'src\s*=\s*["\']\s*javascript:[^"\']*["\']', 'src=""', content, flags=re.IGNORECASE)
    
    # Remove data: URLs (can be used for XSS)
    content = re.sub(r'href\s*=\s*["\']\s*data:[^"\']*["\']', 'href="#"', content, flags=re.IGNORECASE)
    
    # Remove vbscript: URLs
    content = re.sub(r'href\s*=\s*["\']\s*vbscript:[^"\']*["\']', 'href="#"', content, flags=re.IGNORECASE)
    
    return content


def validate_ingest_response(data: dict) -> IngestResponse:
    """Validate and return an ingest response.
    
    Args:
        data: Raw dict from extract_json()
        
    Returns:
        Validated IngestResponse
        
    Raises:
        ValidationError: If validation fails
    """
    errors: list[str] = []
    
    # Check required fields
    if "source_summary" not in data:
        errors.append("Missing required field: 'source_summary'")
    elif not isinstance(data["source_summary"], str):
        errors.append("Field 'source_summary' must be a string")
    
    if "pages" not in data:
        errors.append("Missing required field: 'pages'")
    elif not isinstance(data["pages"], list):
        errors.append("Field 'pages' must be a list")
    else:
        # Validate page count
        if len(data["pages"]) > MAX_PAGES_PER_RESPONSE:
            errors.append(f"Too many pages: {len(data['pages'])} exceeds maximum of {MAX_PAGES_PER_RESPONSE}")
        
        # Validate each page
        for i, page in enumerate(data["pages"]):
            if not isinstance(page, dict):
                errors.append(f"Page {i} must be an object")
                continue
            
            # Check path
            if "path" not in page:
                errors.append(f"Page {i}: missing required field 'path'")
            elif not isinstance(page["path"], str):
                errors.append(f"Page {i}: 'path' must be a string")
            else:
                path = page["path"]
                # Security checks first
                is_safe, error_msg = _is_safe_path(path)
                if not is_safe:
                    errors.append(f"Page {i}: {error_msg}")
                elif not PAGE_PATH_PATTERN.match(path):
                    errors.append(f"Page {i}: invalid path format '{path}' (expected: pages/name.md)")
            
            # Check content
            if "content" not in page:
                errors.append(f"Page {i}: missing required field 'content'")
            elif not isinstance(page["content"], str):
                errors.append(f"Page {i}: 'content' must be a string")
            elif len(page["content"]) == 0:
                errors.append(f"Page {i}: 'content' cannot be empty")
            elif len(page["content"]) > MAX_PAGE_CONTENT_SIZE:
                errors.append(f"Page {i}: 'content' too large ({len(page['content'])} bytes, max: {MAX_PAGE_CONTENT_SIZE})")
            else:
                # Sanitize content to remove dangerous HTML/JS
                page["content"] = sanitize_content(page["content"])
    
    if errors:
        raise ValidationError(f"Ingest response validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return data  # type: ignore[return-value]


def validate_query_relevance_response(data: dict) -> QueryRelevanceResponse:
    """Validate and return a query relevance response.
    
    Args:
        data: Raw dict from extract_json()
        
    Returns:
        Validated QueryRelevanceResponse
        
    Raises:
        ValidationError: If validation fails
    """
    errors: list[str] = []
    
    # Check required fields
    if "pages" not in data:
        errors.append("Missing required field: 'pages'")
    elif not isinstance(data["pages"], list):
        errors.append("Field 'pages' must be a list")
    else:
        # Validate each path
        for i, path in enumerate(data["pages"]):
            if not isinstance(path, str):
                errors.append(f"Path {i} must be a string")
            else:
                # Security checks
                is_safe, error_msg = _is_safe_path(path)
                if not is_safe:
                    errors.append(f"Path {i}: {error_msg}")
                elif not PAGE_PATH_PATTERN.match(path):
                    errors.append(f"Path {i}: invalid format '{path}' (expected: pages/name.md)")
        
        # Check page count
        if len(data["pages"]) > MAX_PAGES_PER_RESPONSE:
            errors.append(f"Too many paths: {len(data['pages'])} exceeds maximum of {MAX_PAGES_PER_RESPONSE}")
    
    if errors:
        raise ValidationError(f"Query relevance response validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return data  # type: ignore[return-value]


def validate_query_answer_response(data: dict) -> QueryAnswerResponse:
    """Validate and return a query answer response.
    
    Args:
        data: Raw dict from extract_json()
        
    Returns:
        Validated QueryAnswerResponse
        
    Raises:
        ValidationError: If validation fails
    """
    errors: list[str] = []
    
    # Check required fields
    if "answer" not in data:
        errors.append("Missing required field: 'answer'")
    elif not isinstance(data["answer"], str):
        errors.append("Field 'answer' must be a string")
    elif len(data["answer"]) == 0:
        errors.append("Field 'answer' cannot be empty")
    
    # Optional fields
    if "save_as" in data and data["save_as"] is not None:
        if not isinstance(data["save_as"], str):
            errors.append("Field 'save_as' must be a string or null")
        else:
            # Security checks
            is_safe, error_msg = _is_safe_path(data["save_as"])
            if not is_safe:
                errors.append(f"Field 'save_as': {error_msg}")
            elif not PAGE_PATH_PATTERN.match(data["save_as"]):
                errors.append(f"Field 'save_as': invalid path format '{data['save_as']}' (expected: pages/name.md)")
    
    if "save_content" in data and data["save_content"] is not None:
        if not isinstance(data["save_content"], str):
            errors.append("Field 'save_content' must be a string or null")
        elif len(data["save_content"]) > MAX_PAGE_CONTENT_SIZE:
            errors.append(f"Field 'save_content' too large ({len(data['save_content'])} bytes, max: {MAX_PAGE_CONTENT_SIZE})")
    
    if errors:
        raise ValidationError(f"Query answer response validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return data  # type: ignore[return-value]


def validate_lint_response(data: dict) -> LintResponse:
    """Validate and return a lint response.
    
    Args:
        data: Raw dict from extract_json()
        
    Returns:
        Validated LintResponse
        
    Raises:
        ValidationError: If validation fails
    """
    errors: list[str] = []
    
    # Check health_score
    if "health_score" not in data:
        errors.append("Missing required field: 'health_score'")
    elif not isinstance(data["health_score"], int):
        errors.append("Field 'health_score' must be an integer")
    elif not (0 <= data["health_score"] <= 100):
        errors.append(f"Field 'health_score' must be between 0 and 100, got: {data['health_score']}")
    
    # Check summary
    if "summary" not in data:
        errors.append("Missing required field: 'summary'")
    elif not isinstance(data["summary"], str):
        errors.append("Field 'summary' must be a string")
    
    # Check issues
    if "issues" not in data:
        errors.append("Missing required field: 'issues'")
    elif not isinstance(data["issues"], list):
        errors.append("Field 'issues' must be a list")
    else:
        valid_severities = {"high", "medium", "low"}
        valid_types = {"orphan", "self_ref", "missing_page", "contradiction", "stale", "gap"}
        
        for i, issue in enumerate(data["issues"]):
            if not isinstance(issue, dict):
                errors.append(f"Issue {i} must be an object")
                continue
            
            # Check type
            if "type" not in issue:
                errors.append(f"Issue {i}: missing required field 'type'")
            elif not isinstance(issue["type"], str):
                errors.append(f"Issue {i}: 'type' must be a string")
            elif issue["type"] not in valid_types:
                errors.append(f"Issue {i}: invalid type '{issue['type']}' (expected one of: {', '.join(valid_types)})")
            
            # Check severity
            if "severity" not in issue:
                errors.append(f"Issue {i}: missing required field 'severity'")
            elif not isinstance(issue["severity"], str):
                errors.append(f"Issue {i}: 'severity' must be a string")
            elif issue["severity"] not in valid_severities:
                errors.append(f"Issue {i}: invalid severity '{issue['severity']}' (expected one of: {', '.join(valid_severities)})")
            
            # Check description
            if "description" not in issue:
                errors.append(f"Issue {i}: missing required field 'description'")
            elif not isinstance(issue["description"], str):
                errors.append(f"Issue {i}: 'description' must be a string")
            
            # Check pages
            if "pages" not in issue:
                errors.append(f"Issue {i}: missing required field 'pages'")
            elif not isinstance(issue["pages"], list):
                errors.append(f"Issue {i}: 'pages' must be a list")
            
            # Check suggestion
            if "suggestion" not in issue:
                errors.append(f"Issue {i}: missing required field 'suggestion'")
            elif not isinstance(issue["suggestion"], str):
                errors.append(f"Issue {i}: 'suggestion' must be a string")
    
    if errors:
        raise ValidationError(f"Lint response validation failed:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return data  # type: ignore[return-value]
