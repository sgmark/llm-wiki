from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table

from wiki_core.store import WikiStore
from wiki_core.ingest import run_ingest
from wiki_core.query import run_query
from wiki_core.lint import run_lint, fix_issues
from wiki_core.llm import LLMError
from wiki_core import build_graph

app = typer.Typer(help="LLM-powered personal wiki", no_args_is_help=True)
console = Console()

DirOpt = Annotated[Optional[Path], typer.Option("--dir", "-d", help="Wiki directory")]


def _resolve_dir(dir: Optional[Path]) -> Path:
    if dir is not None:
        return dir
    if Path("./wiki").is_dir():
        return Path("./wiki")
    return Path("./knowledge")


@app.command()
def init(dir: DirOpt = None):
    """Initialize a new wiki directory."""
    resolved = _resolve_dir(dir)
    store = WikiStore(resolved)
    store.init()
    console.print(f"[green]Wiki initialized at[/green] {resolved.resolve()}")
    console.print(f"  Drop sources in [bold]{resolved}/raw/[/bold], then run [bold]ingest[/bold].")


@app.command()
def ingest(
    source: Annotated[Path, typer.Argument(help="Source file or directory to ingest")],
    dir: DirOpt = None,
):
    """Ingest source documents into the wiki."""
    resolved = _resolve_dir(dir)
    store = WikiStore(resolved)
    store.init()

    # Determine files to ingest
    if source.is_dir():
        supported_extensions = {".txt", ".md", ".markdown"}
        files = [
            f for f in source.iterdir()
            if f.is_file() and f.suffix.lower() in supported_extensions
        ]
        if not files:
            console.print(f"[yellow]No supported files found in directory:[/yellow] {source}")
            console.print(f"Supported formats: {', '.join(supported_extensions)}")
            raise typer.Exit(0)
    else:
        files = [source]

    # Process each file
    total_pages = 0
    for f in files:
        if not f.exists():
            console.print(f"[red]File not found:[/red] {f}")
            continue

        try:
            with console.status(f"Ingesting [bold]{f.name}[/bold]..."):
                summary, pages = run_ingest(f, store)
        except LLMError as e:
            error_msg = f"[red]LLM Error:[/red] {e}"
            if e.retryable:
                error_msg += "\n[yellow]This error may be transient. You can try again.[/yellow]"
            console.print(error_msg)
            continue
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            continue

        console.print(f"[green]Done.[/green] {f.name}: {summary}")
        console.print(f"  Pages written ({len(pages)}):")
        for p in pages:
            console.print(f"    [cyan]{p}[/cyan]")
        total_pages += len(pages)

    console.print(f"\n[green]Total:[/green] {len(files)} file(s), {total_pages} page(s)")


@app.command()
def query(
    question: Annotated[str, typer.Argument(help="Question to ask the wiki")],
    dir: DirOpt = None,
    save: Annotated[bool, typer.Option("--save", "-s", help="Save answer as a wiki page")] = False,
):
    """Query the wiki."""
    resolved = _resolve_dir(dir)
    store = WikiStore(resolved)
    store.init()

    try:
        with console.status("Thinking..."):
            answer, saved = run_query(question, store, save=save)
    except LLMError as e:
        error_msg = f"[red]LLM Error:[/red] {e}"
        if e.retryable:
            error_msg += "\n[yellow]This error may be transient. You can try again.[/yellow]"
        console.print(error_msg)
        raise typer.Exit(1)

    console.print()
    console.print(Markdown(answer))

    if saved:
        console.print(f"\n[green]Answer saved to[/green] [cyan]{saved}[/cyan]")


@app.command()
def lint(
    dir: DirOpt = None,
    fix: Annotated[bool, typer.Option("--fix", help="Attempt to fix issues automatically")] = False,
):
    """Health-check the wiki for issues."""
    resolved = _resolve_dir(dir)
    store = WikiStore(resolved)
    store.init()

    try:
        with console.status("Analyzing wiki..."):
            result = run_lint(store)
    except LLMError as e:
        error_msg = f"[red]LLM Error:[/red] {e}"
        if e.retryable:
            error_msg += "\n[yellow]This error may be transient. You can try again.[/yellow]"
        console.print(error_msg)
        raise typer.Exit(1)

    score = result.get("health_score", "?")
    summary = result.get("summary", "")
    issues = result.get("issues", [])

    score_color = "green" if isinstance(score, int) and score >= 80 else (
        "yellow" if isinstance(score, int) and score >= 50 else "red"
    )
    console.print(f"\n[bold]Health score: [{score_color}]{score}/100[/{score_color}][/bold]")
    console.print(summary)

    if not issues:
        console.print("\n[green]No issues found.[/green]")
        return

    table = Table(title=f"\n{len(issues)} issue(s) found", show_lines=True)
    table.add_column("Severity", width=8)
    table.add_column("Type", width=14)
    table.add_column("Description")
    table.add_column("Suggestion")

    colors = {"high": "red", "medium": "yellow", "low": "blue"}
    for issue in sorted(issues, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.get("severity", "low"), 3)):
        sev = issue.get("severity", "low")
        c = colors.get(sev, "white")
        table.add_row(
            f"[{c}]{sev}[/{c}]",
            issue.get("type", ""),
            issue.get("description", ""),
            issue.get("suggestion", ""),
        )

    console.print(table)

    if fix and issues:
        console.print()
        console.rule("Fixing")
        try:
            report = fix_issues(issues, store, print_fn=console.print)
        except LLMError as e:
            console.print(f"[red]Error while fixing:[/red] {e}")
            raise typer.Exit(1)
        console.rule()
        console.print(f"[green]Fixed:[/green] {len(report['fixed'])}  [yellow]Skipped:[/yellow] {len(report['skipped'])}")


@app.command()
def graph(
    dir: DirOpt = None,
    no_infer: Annotated[bool, typer.Option("--no-infer", help="Skip semantic inference (faster)")] = False,
    open_browser: Annotated[bool, typer.Option("--open", "-o", help="Open graph.html in browser after build")] = False,
    clean: Annotated[bool, typer.Option("--clean", "-c", help="Delete cache and force full rebuild")] = False,
    report: Annotated[bool, typer.Option("--report", "-r", help="Generate graph health report")] = False,
    save: Annotated[bool, typer.Option("--save", "-s", help="Save report to graph/graph-report.md")] = False,
):
    """Build knowledge graph from wiki pages."""
    try:
        with console.status("Building knowledge graph..."):
            build_graph.build_graph(
                infer=not no_infer,
                open_browser=open_browser,
                clean=clean,
                report=report,
                save=save,
            )
        console.print("[green]Graph built successfully![/green]")
    except Exception as e:
        console.print(f"[red]Error building graph:[/red] {e}")
        raise typer.Exit(1)


def main():
    app()


if __name__ == "__main__":
    main()
