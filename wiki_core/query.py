import datetime
from .llm import get_client, chat, extract_json, LLMError
from .store import WikiStore
from .schema_validation import (
    validate_query_relevance_response,
    validate_query_answer_response,
    ValidationError,
)

_RELEVANCE_SYSTEM = """\
Given a wiki index and a question, return the paths of the most relevant pages.
Return JSON only — no other text:
{"pages": ["pages/slug1.md", "pages/slug2.md"]}
Limit to 8 most relevant pages."""

_ANSWER_SYSTEM = """\
You are a wiki assistant. Answer the question using the provided wiki pages.
- Cite pages with [[Page Title]] wikilinks
- Be precise; if the wiki lacks sufficient info, say so clearly
- If the answer would make a valuable permanent wiki page, populate save_as and save_content

Return JSON only — no other text:
{
  "answer": "Markdown answer",
  "save_as": null,
  "save_content": null
}"""

_SAVE_SYSTEM = """\
You are a wiki assistant. The user wants to save the following answer as a wiki page.
Generate a well-structured wiki page for it.

Return JSON only — no other text:
{
  "answer": "Markdown answer (same as provided)",
  "save_as": "pages/slug.md",
  "save_content": "Full wiki page markdown content"
}"""


def run_query(
    question: str, store: WikiStore, save: bool = False
) -> tuple[str, str | None]:
    """Run a query against the wiki.
    
    Args:
        question: The question to ask
        store: WikiStore instance
        save: Whether to save the answer as a new page
        
    Returns:
        Tuple of (answer, saved_path or None)
        
    Raises:
        LLMError: If LLM communication fails after retries
    """
    client = get_client()
    schema = store.read_schema()
    index = store.read_index()

    # Step 1: identify relevant pages
    try:
        rel = chat(client, [
            {"role": "system", "content": _RELEVANCE_SYSTEM},
            {"role": "user", "content": f"Index:\n{index}\n\nQuestion: {question}"},
        ])
    except LLMError as e:
        raise LLMError(
            f"Failed to find relevant pages for query: {e}",
            error_type=e.error_type,
            retryable=e.retryable
        )
    
    try:
        relevance_data = extract_json(rel)
        relevance_data = validate_query_relevance_response(relevance_data)
        relevant_paths = relevance_data.get("pages", [])
    except ValueError:
        relevant_paths = []
    except ValidationError as e:
        # Log warning but continue with empty paths
        relevant_paths = []

    # Step 2: load pages
    pages_content = ""
    for path in relevant_paths:
        content = store.read_page(path)
        if content:
            pages_content += f"\n=== {path} ===\n{content}\n"
    if not pages_content:
        pages_content = "_No relevant pages found in wiki._"

    # Step 3: answer (request save content if --save)
    base_system = _SAVE_SYSTEM if save else _ANSWER_SYSTEM
    system = f"{base_system}\n\nWiki schema / conventions:\n{schema}" if schema else base_system
    
    try:
        ans = chat(client, [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Wiki pages:\n{pages_content}\n\nQuestion: {question}"},
        ])
    except LLMError as e:
        raise LLMError(
            f"Failed to get answer for query: {e}",
            error_type=e.error_type,
            retryable=e.retryable
        )
    
    try:
        data = extract_json(ans)
        data = validate_query_answer_response(data)
    except ValueError:
        data = {"answer": ans}
    except ValidationError as e:
        # Log warning but continue with just the answer
        data = {"answer": ans}

    answer = data.get("answer", "")

    saved_path: str | None = None
    if save and data.get("save_as") and data.get("save_content"):
        saved_path = data["save_as"]
        store.write_page(saved_path, data["save_content"])
        store.rebuild_index()

    store.append_log(
        "query",
        question[:60],
        f"Pages consulted: {', '.join(relevant_paths) or 'none'}",
    )

    return answer, saved_path
