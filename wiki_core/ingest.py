from pathlib import Path
import shutil

# File size limits for source documents
MAX_SOURCE_SIZE = 10 * 1024 * 1024  # 10 MB
MIN_SOURCE_SIZE = 1  # 1 byte (reject empty files)

from .llm import get_client, chat, extract_json, LLMError
from .store import WikiStore
from .schema_validation import validate_ingest_response, ValidationError

_SYSTEM = """\
You are a wiki maintainer. You maintain a structured personal knowledge base as markdown files.

When given a source document, you will:
1. Extract all significant entities, concepts, facts, and insights
2. Create or update wiki pages — one page per entity/concept/topic
3. Cross-reference pages using [[Page Title]] wikilink syntax
4. Keep content dense, factual, and well-organized

Wiki page format:
```markdown
---
tags: [tag1, tag2]
updated: YYYY-MM-DD
sources: [filename]
---

# Page Title

Brief summary paragraph.

## Details

...

## Related
- [[Other Page]]
```

Return a JSON object with EXACTLY this structure — no other text:
{
  "source_summary": "One-sentence summary of the source",
  "pages": [
    {
      "path": "pages/slug-name.md",
      "content": "Full markdown content"
    }
  ]
}"""


def run_ingest(source: Path, store: WikiStore) -> tuple[str, list[str]]:
    """Ingest a source document into the wiki.
    
    Args:
        source: Path to the source document
        store: WikiStore instance
        
    Returns:
        Tuple of (summary, list of page paths written)
        
    Raises:
        LLMError: If LLM communication fails after retries
        FileNotFoundError: If source file doesn't exist
        ValueError: If source file is too large, too small, or LLM response cannot be parsed
    """
    # Validate source file size before reading
    try:
        file_size = source.stat().st_size
    except OSError as e:
        raise FileNotFoundError(f"Cannot access source file '{source}': {e}")
    
    if file_size < MIN_SOURCE_SIZE:
        raise ValueError(f"Source file '{source.name}' is empty or too small (minimum: {MIN_SOURCE_SIZE} byte)")
    
    if file_size > MAX_SOURCE_SIZE:
        raise ValueError(
            f"Source file '{source.name}' is too large ({file_size} bytes). "
            f"Maximum allowed size: {MAX_SOURCE_SIZE} bytes ({MAX_SOURCE_SIZE // (1024*1024)} MB)"
        )
    
    # Copy source file to raw directory (if not already there)
    store.init()  # Ensure directories exist
    raw_path = store.raw_dir / source.name
    if not raw_path.exists():
        shutil.copy2(source, raw_path)
    
    client = get_client()

    schema = store.read_schema()
    system = f"{_SYSTEM}\n\nWiki schema / conventions:\n{schema}" if schema else _SYSTEM

    index = store.read_index()
    previews = store.page_previews(max_pages=20, max_chars_each=500)
    existing = f"\n\nExisting pages (excerpts):\n{previews}" if previews else ""

    user_msg = (
        f"Current wiki index:\n{index}"
        f"{existing}\n\n"
        f"Source document to ingest (filename: {source.name}):\n"
        f"{source.read_text()}\n\n"
        "Create or update wiki pages for all key entities, concepts, and topics."
    )

    try:
        response = chat(client, [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ])
    except LLMError as e:
        raise LLMError(
            f"Failed to ingest '{source.name}': {e}",
            error_type=e.error_type,
            retryable=e.retryable
        )

    try:
        data = extract_json(response)
    except ValueError as e:
        raise ValueError(f"Failed to parse LLM response for '{source.name}': {e}")

    try:
        data = validate_ingest_response(data)
    except ValidationError as e:
        raise ValueError(f"LLM response validation failed for '{source.name}': {e}")

    pages_written: list[str] = []
    for page in data.get("pages", []):
        path = page.get("path", "")
        content = page.get("content", "")
        if path and content:
            store.write_page(path, content)
            pages_written.append(path)

    store.rebuild_index()
    summary = data.get("source_summary", "")
    store.append_log(
        "ingest",
        source.name,
        f"Summary: {summary}\nPages written: {', '.join(pages_written)}",
    )

    return summary, pages_written
