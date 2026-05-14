import datetime
from pathlib import Path

def validate_path(root: Path, path: str) -> Path:
    """Validate that a path stays within the wiki pages directory.
    
    This function implements multiple layers of defense against path traversal attacks:
    1. Checks for dangerous characters (null bytes, newlines)
    2. Normalizes Windows path separators to Unix-style for cross-platform compatibility
    3. Checks for path traversal sequences (..)
    4. Ensures path starts with 'pages/'
    5. Verifies resolved path is within root/pages/ directory
    
    Args:
        root: The wiki root directory
        path: Relative path to validate (must be within pages/)
        
    Returns:
        The resolved absolute path if valid
        
    Raises:
        ValueError: If the path is invalid or attempts to escape the pages directory
    """
    # Check for null bytes (path traversal via null injection)
    if "\x00" in path:
        raise ValueError("Path contains invalid characters (null bytes)")
    
    # Check for newlines (path traversal via newline injection)
    if "\n" in path or "\r" in path:
        raise ValueError("Path contains invalid characters (newlines)")
    
    # Normalize Windows path separators to Unix-style (for cross-platform compatibility)
    path = path.replace("\\", "/")
    
    # Check for path traversal sequences
    if ".." in path:
        raise ValueError(f"Path traversal detected: path contains '..' sequence")
    
    # Path must start with 'pages/'
    if not path.startswith("pages/"):
        raise ValueError(f"Path must start with 'pages/', got: '{path}'")
    
    # Resolve the full path
    full = (root / path).resolve()
    root_resolved = root.resolve()
    pages_dir_resolved = (root / "pages").resolve()
    
    # Ensure the resolved path is within root/pages/ directory
    try:
        full.relative_to(pages_dir_resolved)
    except ValueError:
        raise ValueError(f"Path traversal detected: '{path}' escapes the pages directory")
    
    return full

SCHEMA_TEMPLATE = """\
# Wiki Schema

## Page Conventions

- Use `[[Page Title]]` for cross-references between pages
- YAML frontmatter on every page:
  ```yaml
  ---
  tags: [tag1, tag2]
  updated: YYYY-MM-DD
  sources: [source-filename]
  ---
  ```
- Standard sections: **Summary**, **Details**, **Related**
- File slugs: `lowercase-hyphenated.md`

## Directory Structure

- `pages/`  — all wiki pages (LLM-maintained)
- `raw/`    — source documents (immutable, user-managed)
- `index.md` — catalog of all pages with one-line summaries
- `log.md`   — append-only chronological event log
- `schema.md` — this file; wiki conventions

## Index Format

One entry per page:
```
- [[Page Title]](pages/slug.md) — one-line summary
```

## Log Format

One entry per event:
```
## [YYYY-MM-DD] event_type | Title
```
"""


class WikiStore:
    def __init__(self, root: Path):
        self.root = root
        self.pages_dir = root / "pages"
        self.raw_dir = root / "raw"
        self.index_path = root / "index.md"
        self.log_path = root / "log.md"
        self.schema_path = root / "schema.md"

    def init(self):
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self.index_path.write_text("# Wiki Index\n\n_No pages yet._\n")
        if not self.log_path.exists():
            self.log_path.write_text("# Wiki Log\n\n")
        if not self.schema_path.exists():
            self.schema_path.write_text(SCHEMA_TEMPLATE)

    def read_index(self) -> str:
        if self.index_path.exists():
            return self.index_path.read_text()
        return "# Wiki Index\n\n_Empty._\n"

    def write_index(self, content: str):
        self.index_path.write_text(content)

    def rebuild_index(self):
        pages = self.list_pages()
        lines = ["# Wiki Index\n"]
        for p in sorted(pages):
            content = self.read_page(p)
            title = Path(p).stem.replace("-", " ").title()
            summary = ""
            if content:
                in_frontmatter = False
                past_title = False
                fm_count = 0
                for line in content.splitlines():
                    if line.strip() == "---":
                        fm_count += 1
                        in_frontmatter = fm_count == 1
                        continue
                    if in_frontmatter:
                        continue
                    if line.startswith("# "):
                        title = line[2:].strip()
                        past_title = True
                        continue
                    if past_title and line.strip() and not line.startswith("#"):
                        summary = line.strip()[:120]
                        break
            lines.append(f"- [[{title}]]({p}) — {summary}")
        self.write_index("\n".join(lines) + "\n")

    def append_log(self, event_type: str, title: str, details: str = ""):
        date = datetime.date.today().isoformat()
        entry = f"\n## [{date}] {event_type} | {title}\n"
        if details:
            entry += f"\n{details}\n"
        with open(self.log_path, "a") as f:
            f.write(entry)

    def read_page(self, path: str) -> str | None:
        full = validate_path(self.root, path)
        return full.read_text() if full.exists() else None

    def write_page(self, path: str, content: str):
        full = validate_path(self.root, path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)

    def list_pages(self) -> list[str]:
        if not self.pages_dir.exists():
            return []
        return sorted(str(p.relative_to(self.root)) for p in self.pages_dir.glob("*.md"))

    def read_schema(self) -> str:
        return self.schema_path.read_text() if self.schema_path.exists() else ""

    def page_previews(self, max_pages: int = 30, max_chars_each: int = 600) -> str:
        """Compact multi-page context for LLM prompts."""
        out = []
        for p in self.list_pages()[:max_pages]:
            content = self.read_page(p) or ""
            out.append(f"--- {p} ---\n{content[:max_chars_each]}")
        return "\n\n".join(out)
