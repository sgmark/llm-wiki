# wiki

A CLI tool that builds and maintains a personal knowledge base using an LLM. You feed it documents; it writes and cross-references a structured wiki of markdown files that gets richer over time.

Instead of re-deriving answers from raw documents on every query, the LLM compiles knowledge once and keeps it current — updating pages, flagging contradictions, and maintaining cross-references as new sources arrive.

## Install

Requires [uv](https://github.com/astral-sh/uv).

```bash
git clone <repo>
cd wiki
uv tool install .
```

The `wiki` command is now available globally.

To pick up code changes after editing:

```bash
uv tool install --reinstall .
```

## Setup

Configure the LLM connection via environment variables:

```bash
export WIKI_LLM_URL="http://your-host:port/v1"  # Your LLM server URL
export WIKI_API_KEY="your-api-key"               # Your API key (or "EMPTY" if not needed)
export WIKI_LLM_MODEL="your-model-name"          # Model name (e.g., "gpt-4", "qwen-2.5-72b")
```

Or set them in your shell profile (`~/.bashrc`, `~/.zshrc`, etc.) for persistent configuration:

```bash
echo 'export WIKI_LLM_URL="http://localhost:8000/v1"' >> ~/.bashrc
echo 'export WIKI_API_KEY="EMPTY"' >> ~/.bashrc
echo 'export WIKI_LLM_MODEL="gpt-4"' >> ~/.bashrc
source ~/.bashrc
```

The tool will warn you if these are not set and defaults are being used.

## Usage

### Initialize

```bash
wiki init
wiki init --dir ~/Projects/myproject/wiki
```

Creates the wiki directory with `pages/`, `raw/`, `index.md`, `log.md`, and `schema.md`. Defaults to `./knowledge`, or `./wiki` if that directory already exists in the current folder.

### Ingest a document

```bash
wiki ingest path/to/article.md
wiki ingest paper.pdf --dir ~/Projects/myproject/wiki
```

The LLM reads the source, extracts entities and concepts, and writes or updates wiki pages for each. A single source typically touches 5–25 pages. The index is rebuilt automatically after each ingest.

### Query

```bash
wiki query "What are the guarantees that cross subsystem boundaries?"
wiki query "Compare X and Y" --save
```

Two-step: the LLM identifies relevant pages from the index, reads them, then synthesizes an answer with `[[wikilink]]` citations. `--save` writes the answer as a new wiki page so it compounds into the knowledge base.

### Lint

```bash
wiki lint
wiki lint --fix
```



Checks the wiki for structural and semantic issues:

- **Structural** (programmatic): broken wikilinks, orphan pages, self-references
- **Semantic** (LLM): contradictions between pages, stale content, knowledge gaps

`--fix` attempts to resolve each issue — self-references are removed programmatically; missing pages, contradictions, and gaps are addressed by the LLM. Progress is printed per issue. Orphans are reported but not auto-fixed.

### Build Graph

```bash
wiki graph
wiki graph --open
wiki graph --save
wiki graph --report
```

Builds an interactive knowledge graph from wiki pages:

- `--open` / `-o`: Open `graph.html` in browser after build
- `--save` / `-s`: Save health report to `graph/graph-report.md`
- `--report` / `-r`: Print health report to console
- `--no-infer`: Skip semantic inference (faster)
- `--clean` / `-c`: Delete cache and force full rebuild

Output:
- `graph/graph.html` — interactive visualization (vis.js)
- `graph/graph.json` — raw node/edge data (cached by SHA256)

## Wiki directory layout

```
knowledge/          ← default wiki root (or ./wiki if it exists)
  pages/            ← all wiki pages, one concept per file
  raw/              ← your source documents (untouched)
  index.md          ← auto-maintained catalog of all pages
  log.md            ← append-only record of ingests, queries, lints
  schema.md         ← wiki conventions; edit this to customize behaviour
```

The LLM reads `schema.md` on every operation. Edit it to change page format, naming conventions, or what to emphasize during ingest.

## Tips

- Run `wiki lint` periodically as the wiki grows — it finds cross-page contradictions that are hard to spot manually.
- Use `--save` on queries that produce useful synthesis; good answers compound just like ingested sources.
- The wiki is plain markdown — open it in Obsidian for graph view, backlink tracking, and Dataview queries.
- The wiki directory is a git repo candidate: `git init` inside it gives you full history of how knowledge evolved.
- Drop source files in `raw/` as a staging area, then ingest them one at a time to stay involved in what gets added.

## 致谢
本项目复用和集成了以下开源项目：

- 本项目基于 [Andrej Karpathy](https://github.com/karpathy) 的 [LLM Wiki 模式](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) 实现。
- [Jeremy Tregunna- llm-wiki](https://codeberg.org/canoozie/wiki)
- [SamurAIGPT - LLM Wiki Agent](https://github.com/SamurAIGPT/llm-wiki-agent)


