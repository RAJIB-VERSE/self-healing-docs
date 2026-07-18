# Memory — Progress Log

Purpose: keep any AI session up to date on project state without re-reading the
whole codebase. Update at every phase gate and for every decision that changes
Rules/Architecture (Rules.md §6).

## Current state

- **Phase**: 1 complete → starting Phase 2 (change detection)
- **Tests**: 20 passing (`pytest -q`), ruff clean
- **Env**: Windows, git-bash; venv at `.venv/` (`.venv/Scripts/python`); Python 3.14 local
  (project targets 3.11+ — CI/Docker will pin 3.11)

## Decisions made (beyond the planning docs)

1. **User decisions at kickoff**: user said "continue with the build" without answering
   language/provider questions → defaults chosen per PRD: Python 3.11+, OpenAI primary
   with Anthropic option behind `llm-provider` input.
2. **Embedding comparison is brute-force in-process** for MVP (embedder.py); ChromaDB
   is a between-run cache only, layered on in Phase 4. Rationale: hundreds of items,
   no persistence edge cases in tests.
3. **Module-level constants (e.g. `DEFAULT_TIMEOUT`) are NOT extracted as chunks yet.**
   Doc sections mentioning only constants currently get no heuristic links. Candidate
   Phase 2/3 enhancement if fixture testing shows it matters.
4. **`(intro)` pseudo-heading** for pre-first-heading markdown content; level 0.
5. **Doc section end_lineno** = last content line (trailing blank lines trimmed by
   splitlines semantics) — test_line_numbers_track_source documents this.

## File map (what exists and works)

- `src/dochealer/models.py` — all pipeline models (pydantic v2)
- `src/dochealer/config.py` — Settings + INDEX_VERSION=1 + branch/label constants
- `src/dochealer/indexing/code_parser.py` — AST → CodeChunk (fn/class/method/cli/config)
- `src/dochealer/indexing/doc_parser.py` — markdown → DocSection + code_refs
- `src/dochealer/indexing/embedder.py` — OpenAIEmbedder + similarity_links (injectable)
- `src/dochealer/indexing/linker.py` — heuristic+embedding graph, save/load w/ version gate
- `src/dochealer/main.py` — `dochealer index` CLI; `run` command lands Phase 4
- `tests/` — conftest (FakeEmbedder), parser/linker suites, fixture repo

## Gotchas for future sessions

- `ast.unparse` renders defaults as `include_inactive: bool=False` (no space around `=`) —
  tests assert this exact form.
- Windows: use `.venv/Scripts/python`, forward slashes work in git-bash; `python3` alias
  is broken on this machine, plain `python` is 3.14.
- Fixture repo gets a `.dochealer/` dir when the CLI smoke test runs — delete it; it must
  not be committed (tests build graphs in-memory).

## Next up (Phase 2)

`detection/diff_parser.py` (git diff -U0 → changed ranges → ChangedChunks),
`detection/change_filter.py`, `detection/staleness.py` + `llm/client.py`,
tests incl. e2e-with-FakeLLM on fixture repo.
