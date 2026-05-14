import re
from pathlib import Path as FilePath
from .llm import get_client, chat, extract_json, LLMError
from .store import WikiStore
from .schema_validation import validate_lint_response, ValidationError

WIKILINK_RE = re.compile(r'\[\[([^\]]+)\]\]')

_SEMANTIC_SYSTEM = """\
You are a wiki semantic auditor. Structural issues (broken links, orphans, self-references) have already been checked programmatically — do NOT report those.

Your job: find only semantic issues:
- Contradictions: two pages making conflicting claims
- Stale content: claims superseded by information on other pages
- Knowledge gaps: important topics mentioned across pages but lacking their own page

Return JSON only — no other text:
{
  "health_score": 0-100,
  "summary": "Two-sentence assessment of content quality",
  "issues": [
    {
      "type": "contradiction|stale|gap",
      "severity": "high|medium|low",
      "description": "Specific description",
      "pages": ["pages/a.md"],
      "suggestion": "How to fix"
    }
  ]
}"""

_FIX_SYSTEM = """\
You are a wiki editor. Fix the described issue by returning updated or new page content.

Return JSON only — no other text:
{
  "fixes": [
    {"path": "pages/slug.md", "content": "Full updated markdown content"}
  ]
}"""


def _extract_title(content: str) -> str | None:
    for line in content.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _structural_lint(store: WikiStore) -> list[dict]:
    issues: list[dict] = []

    title_to_path: dict[str, str] = {}
    path_to_title: dict[str, str] = {}
    path_to_links: dict[str, set[str]] = {}

    for path in store.list_pages():
        content = store.read_page(path) or ""
        title = _extract_title(content) or FilePath(path).stem
        title_to_path[title] = path
        path_to_title[path] = title
        path_to_links[path] = set(WIKILINK_RE.findall(content))

    inbound: dict[str, set[str]] = {p: set() for p in path_to_links}
    for src, links in path_to_links.items():
        for linked_title in links:
            target = title_to_path.get(linked_title)
            if target and target != src:
                inbound[target].add(src)

    orphans = sorted(p for p, inb in inbound.items() if not inb)
    if orphans:
        issues.append({
            "type": "orphan",
            "severity": "medium",
            "description": f"{len(orphans)} page(s) have no inbound links.",
            "pages": orphans,
            "suggestion": "Add [[links]] to these pages from related pages.",
        })

    self_refs = sorted(
        p for p, links in path_to_links.items()
        if path_to_title[p] in links
    )
    if self_refs:
        issues.append({
            "type": "self_ref",
            "severity": "low",
            "description": f"{len(self_refs)} page(s) link to themselves in their Related section.",
            "pages": self_refs,
            "suggestion": "Remove self-references from Related sections.",
        })

    broken: dict[str, list[str]] = {}
    for src, links in path_to_links.items():
        src_title = path_to_title[src]
        for linked_title in links:
            if linked_title != src_title and linked_title not in title_to_path:
                broken.setdefault(linked_title, []).append(src)

    for missing_title, sources in sorted(broken.items()):
        issues.append({
            "type": "missing_page",
            "severity": "high",
            "description": f"[[{missing_title}]] is linked from {len(sources)} page(s) but doesn't exist.",
            "pages": sources[:5],
            "suggestion": f"Create a page titled '{missing_title}' or correct the links.",
            "_missing_title": missing_title,
        })

    return issues


def _fix_self_refs(issue: dict, store: WikiStore) -> int:
    fixed = 0
    for path in issue["pages"]:
        content = store.read_page(path)
        if not content:
            continue
        title = _extract_title(content) or ""
        new_content = re.sub(rf'- \[\[{re.escape(title)}\]\]\n?', '', content)
        new_content = re.sub(rf'\[\[{re.escape(title)}\]\],?\s*', '', new_content)
        new_content = re.sub(r'\n{3,}', '\n\n', new_content).rstrip() + '\n'
        if new_content != content:
            store.write_page(path, new_content)
            fixed += 1
    return fixed


def _fix_with_llm(issue: dict, store: WikiStore, client) -> list[str]:
    """Use LLM to fix an issue. Returns list of paths written."""
    index = store.read_index()
    pages_context = ""
    for path in issue.get("pages", []):
        content = store.read_page(path)
        if content:
            pages_context += f"\n=== {path} ===\n{content}\n"

    user_msg = (
        f"Issue to fix:\nType: {issue['type']}\n"
        f"Description: {issue['description']}\n"
        f"Suggestion: {issue['suggestion']}\n\n"
        f"Wiki index (for context):\n{index}\n"
        f"Relevant pages:\n{pages_context}"
    )

    try:
        response = chat(client, [
            {"role": "system", "content": _FIX_SYSTEM},
            {"role": "user", "content": user_msg},
        ])
    except LLMError as e:
        # Re-raise with context about which issue failed
        raise LLMError(
            f"Failed to fix issue ({issue['type']}): {e}",
            error_type=e.error_type,
            retryable=e.retryable
        )

    try:
        data = extract_json(response)
    except ValueError:
        return []

    written = []
    for fix in data.get("fixes", []):
        path = fix.get("path", "")
        content = fix.get("content", "")
        if path and content:
            store.write_page(path, content)
            written.append(path)

    return written


def fix_issues(issues: list[dict], store: WikiStore, print_fn=None) -> dict[str, list[str]]:
    """Fix issues in-place. print_fn(msg) is called for live progress if provided.
    
    Args:
        issues: List of issue dicts from _structural_lint or semantic analysis
        store: WikiStore instance
        print_fn: Optional callback for progress updates
        
    Returns:
        Dict with 'fixed' and 'skipped' lists
        
    Raises:
        LLMError: If LLM communication fails while fixing issues
    """
    client = get_client()
    report: dict[str, list[str]] = {"fixed": [], "skipped": []}
    _print = print_fn or (lambda _: None)

    for issue in issues:
        itype = issue["type"]
        desc = issue["description"][:60]

        if itype == "self_ref":
            n = _fix_self_refs(issue, store)
            if n:
                report["fixed"].append(f"self_ref: removed from {n} page(s)")
                _print(f"[green]fixed[/green] self_ref ({n} page(s))")
            else:
                report["skipped"].append("self_ref: nothing changed")
                _print(f"[dim]skip[/dim] self_ref: nothing to remove")

        elif itype in ("missing_page", "contradiction", "stale", "gap"):
            _print(f"[yellow]fixing[/yellow] {itype}: {desc}...")
            try:
                written = _fix_with_llm(issue, store, client)
            except LLMError as e:
                report["skipped"].append(f"{itype}: LLM error — {e}")
                _print(f"[red]error[/red] {itype}: {e}")
                continue
            except Exception as e:
                report["skipped"].append(f"{itype}: error — {e}")
                _print(f"[red]error[/red] {itype}: {e}")
                continue
            if written:
                report["fixed"].extend(written)
                _print(f"[green]fixed[/green] {itype}: wrote {', '.join(written)}")
            else:
                report["skipped"].append(f"{itype}: LLM returned no fixes")
                _print(f"[dim]skip[/dim] {itype}: LLM returned no fixes")

        else:
            report["skipped"].append(f"{itype}: not auto-fixable")
            _print(f"[dim]skip[/dim] {itype}: not auto-fixable")

    if report["fixed"]:
        store.rebuild_index()

    return report


def run_lint(store: WikiStore) -> dict:
    """Run linting on the wiki.
    
    Args:
        store: WikiStore instance
        
    Returns:
        Dict with health_score, summary, and issues list
        
    Raises:
        LLMError: If LLM communication fails during semantic analysis
    """
    pages = store.list_pages()
    if not pages:
        return {"health_score": 100, "summary": "No pages to check.", "issues": []}

    structural_issues = _structural_lint(store)

    client = get_client()
    schema = store.read_schema()
    system = f"{_SEMANTIC_SYSTEM}\n\nWiki schema:\n{schema}" if schema else _SEMANTIC_SYSTEM

    full_content = "\n".join(
        f"=== {p} ===\n{store.read_page(p) or ''}" for p in pages
    )

    try:
        response = chat(client, [
            {"role": "system", "content": system},
            {"role": "user", "content": f"Wiki pages:\n{full_content}"},
        ])
    except LLMError as e:
        raise LLMError(
            f"Failed to run semantic lint: {e}",
            error_type=e.error_type,
            retryable=e.retryable
        )

    try:
        semantic_data = extract_json(response)
        semantic_data = validate_lint_response(semantic_data)
    except ValueError:
        semantic_data = {"health_score": 80, "summary": "Semantic check failed to parse.", "issues": []}
    except ValidationError as e:
        semantic_data = {"health_score": 80, "summary": f"Semantic check validation failed: {e}", "issues": []}

    all_issues = structural_issues + semantic_data.get("issues", [])

    high = sum(1 for i in structural_issues if i["severity"] == "high")
    med  = sum(1 for i in structural_issues if i["severity"] == "medium")
    score = max(0, semantic_data.get("health_score", 80) - high * 5 - med * 2)

    store.append_log(
        "lint",
        "health check",
        f"Score: {score} | Structural: {len(structural_issues)} | Semantic: {len(semantic_data.get('issues', []))}",
    )

    return {
        "health_score": score,
        "summary": semantic_data.get("summary", ""),
        "issues": all_issues,
    }
