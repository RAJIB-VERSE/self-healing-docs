# Architecture — Self-Healing Technical Documentation

## 1. High-Level Flow

```
                         ┌─────────────────────────────────────────────┐
   PR opened/updated     │            GitHub Action (Docker)           │
  ───────────────────►   │                                             │
                         │  1. INDEX      2. DETECT       3. REPAIR    │
                         │  ┌─────────┐   ┌───────────┐   ┌─────────┐  │
   repo checkout ──────► │  │ code    │   │ git diff  │   │ correct │  │
                         │  │ parser  │──►│ → chunks  │──►│ + valid │  │
   docs/ + README ─────► │  │ doc     │   │ → filter  │   │ ate     │  │
                         │  │ parser  │   │ → suspects│   └────┬────┘  │
                         │  │ linker  │   │ → verify  │        │       │
                         │  └────┬────┘   └───────────┘        │       │
                         │       ▼                             ▼       │
                         │  .dochealer/index.json      4. REPORT       │
                         │  (embeddings in ChromaDB)   fix PR/comment  │
                         └─────────────────────────────────────────────┘
```

Pipeline stages (each a pure module, callable without GitHub for local testing):

1. **INDEX** — parse code → chunks; parse docs → sections; build link graph; persist.
2. **DETECT** — parse PR diff → changed chunks → meaningful-change filter → suspect
   sections (graph lookup) → LLM staleness verification.
3. **REPAIR** — per confirmed-stale section: targeted correction → LLM validation pass →
   confidence routing (auto-fix vs. flag).
4. **REPORT** — GitHub side effects: fix branch + PR, review comments, summary comment.

## 2. File & Folder Structure

```
self-healing-docs/
├── PRD.md  Architecture.md  Rules.md  Phases.md  Design.md  Memory.md
├── README.md
├── action.yml                     # GitHub Action definition
├── Dockerfile                     # Action container
├── pyproject.toml                 # deps + tooling config
├── .gitignore
├── src/dochealer/
│   ├── __init__.py
│   ├── config.py                  # Settings dataclass; env/input parsing
│   ├── models.py                  # CodeChunk, DocSection, Link, ChangedChunk,
│   │                              # StalenessVerdict, Correction, RunReport
│   ├── indexing/
│   │   ├── __init__.py
│   │   ├── code_parser.py         # Python AST → CodeChunk list
│   │   ├── doc_parser.py          # Markdown → DocSection list (+ code refs)
│   │   ├── embedder.py            # OpenAI embeddings + ChromaDB persistence
│   │   └── linker.py              # heuristic + embedding links → LinkGraph
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── diff_parser.py         # unified diff → per-file changed line ranges
│   │   ├── change_filter.py       # meaningful vs. ignorable changes
│   │   └── staleness.py           # LLM verification of suspect sections
│   ├── repair/
│   │   ├── __init__.py
│   │   ├── corrector.py           # targeted rewrite generation
│   │   └── validator.py           # second-pass quality gate
│   ├── llm/
│   │   ├── __init__.py
│   │   └── client.py              # provider-agnostic chat + JSON-mode helper
│   ├── github/
│   │   ├── __init__.py
│   │   ├── pr_writer.py           # branch, commit, fix-PR creation
│   │   └── commenter.py           # summary + review comments
│   ├── report.py                  # RunReport → markdown comment / JSON output
│   └── main.py                    # entrypoint: orchestrates the 4 stages
├── tests/
│   ├── fixtures/sample_repo/      # tiny fake repo: src/ + docs/ + README
│   ├── test_code_parser.py
│   ├── test_doc_parser.py
│   ├── test_linker.py
│   ├── test_diff_parser.py
│   ├── test_change_filter.py
│   └── test_pipeline.py           # end-to-end on fixture repo, LLM mocked
└── .github/workflows/
    ├── ci.yml                     # lint + tests on this repo
    └── self-test.yml              # dogfood: run the Action on itself
```

## 3. Tech Stack

| Component | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | AST module for parsing; single language for Action + pipeline |
| Embeddings | OpenAI `text-embedding-3-small` | cheap; only used for linker |
| Vector store | ChromaDB (persistent, file-based) | lives in `.dochealer/chroma/`; no server |
| LLM | GPT-4o (default) or Claude via `llm-provider` input | JSON-mode structured outputs |
| Git/GitHub | PyGithub + `git` CLI (diff via subprocess) | PR + comment APIs |
| CI/CD | GitHub Actions, Docker container action | `python:3.11-slim` base |
| Testing | pytest; LLM/network mocked via fakes | fixture repo for e2e |
| Lint/format | ruff | configured in pyproject.toml |

## 4. Data Model (models.py)

```python
CodeChunk(id, path, kind, name, qualname, signature, docstring, source, lineno, end_lineno)
    # kind: "function" | "class" | "method" | "config" | "cli"
    # id = f"{path}::{qualname}"  (stable across runs)

DocSection(id, path, heading_path, level, content, code_refs, lineno, end_lineno)
    # id = f"{path}#{slug(heading_path)}"

Link(doc_id, chunk_id, source, score)     # source: "heuristic" | "embedding"
LinkGraph(chunks, sections, links)        # + lookup: chunk_id -> [DocSection]

ChangedChunk(chunk_id, change_kind, old_source, new_source)
    # change_kind: "modified" | "added" | "removed"

StalenessVerdict(section_id, stale, diagnosis, confidence)      # from LLM, JSON-mode
Correction(section_id, new_content, validated, confidence, todo_markers)
RunReport(verified_ok, fixed, flagged, skipped, fix_pr_url)
```

## 5. Key Design Decisions

1. **Index lives in the repo** (`.dochealer/index.json`), rebuilt when missing or when
   docs/code parsing versions change. Chroma DB is a *cache* (rebuildable from index.json);
   it is gitignored, and cached between Action runs via `actions/cache`.
2. **Filter before LLM** — the meaningful-change filter and link-graph lookup are pure
   Python and run first, so PRs with no doc impact cost $0 in LLM calls.
3. **Provider-agnostic LLM client** — one `chat_json(system, user, schema)` function;
   OpenAI and Anthropic implementations behind it. Model IDs are config, not code.
4. **Confidence routing** — verification and correction both return confidence ∈ [0,1];
   `min(verify_conf, correct_conf) ≥ threshold` → auto-fix path, else flag path.
5. **Idempotence / loop safety** — fix PRs carry the `dochealer` label and a marker in the
   branch name (`dochealer/fix-<pr#>`); the Action exits early on its own PRs. Summary
   comments are upserted (find-and-edit by hidden HTML marker), not duplicated.
6. **Everything testable offline** — GitHub and LLM clients are injected; tests use fakes.

## 6. Execution Sequence (main.py)

```
load config → checkout is already done by runner
→ load or build index (INDEX)
→ git diff base...head → ChangedChunks → filter (DETECT-a)
→ suspects = graph.affected_sections(changed) (DETECT-b)
→ verdicts = staleness.verify(suspects, cap=N) (DETECT-c, LLM)
→ for stale: correction = corrector.generate → validator.check (REPAIR, LLM)
→ route by confidence → pr_writer / commenter (REPORT)
→ write outputs (GITHUB_OUTPUT) + exit 0 (never fail the host PR on findings)
```
