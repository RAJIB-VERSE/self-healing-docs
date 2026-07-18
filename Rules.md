# Rules — Boundaries for AI-Assisted Development

These rules govern how the AI builds and modifies this project. They are binding for every
phase in Phases.md.

## 1. Libraries

**Allowed (and only these, plus stdlib):**
- `openai` (embeddings + GPT-4o), `anthropic` (Claude option)
- `chromadb` (vector store)
- `PyGithub` (GitHub API)
- `pydantic` v2 (models/validation)
- `pytest`, `ruff` (dev only)

**Forbidden:**
- LangChain / LlamaIndex or any agent framework — the pipeline is explicit, deterministic code.
- Heavyweight parsing deps (tree-sitter, etc.) for MVP — Python's `ast` module only.
- Any networking library beyond the SDKs above (no raw `requests` calls to LLM APIs).
- No new dependencies without updating this file and Architecture.md first.

## 2. Code Standards

- Python 3.11+, full type hints on public functions, ruff-clean.
- Every module in `src/dochealer/` stays importable and runnable **without** GitHub or
  network access — external clients are injected, never constructed at import time.
- Dataclasses/pydantic models from `models.py` are the only data passed between stages;
  no loose dicts crossing module boundaries.
- Stable IDs (`path::qualname`, `path#heading-slug`) must never change format — the
  persisted index depends on them. If the format must change, bump `INDEX_VERSION` so
  stale indexes are rebuilt, and note it in Memory.md.

## 3. LLM Usage Rules

- **Filter first, LLM second**: no LLM call may run before the meaningful-change filter
  and link-graph lookup have narrowed the candidate set.
- All LLM calls go through `llm/client.py` — no direct SDK calls elsewhere.
- All LLM responses must be JSON-mode with a pydantic schema; parse failures retry once,
  then treat the item as "flag for review" (never crash, never guess).
- Hard caps enforced in config: max 20 sections verified per run, max 10 corrections per
  run, max ~8k tokens of code context per prompt. Exceeding a cap → remaining items are
  flagged, and the summary comment says so.
- Prompts may include only: code chunk sources, diffs, and doc section text. **Never**
  include file contents outside indexed chunks, environment variables, or anything from
  `.env`, `secrets`, or CI context.

## 4. Error Handling

- The Action must **never fail the host PR** because docs are stale or an API errored.
  Findings are reported via comments; infrastructure errors exit 0 with a warning comment
  and a non-empty `report-json` explaining what was skipped.
- Every external call (LLM, GitHub, git subprocess) is wrapped with: explicit timeout,
  one retry with backoff for transient errors, then graceful degradation (skip item,
  record in report).
- No bare `except:`. Catch specific exceptions; log with the stdlib `logging` module.
- Malformed input files (unparseable Python, broken markdown) are skipped with a warning,
  never fatal.

## 5. Git / GitHub Behavior

- The AI never pushes to remotes, never creates real PRs, and never calls live APIs during
  development — that code runs only inside the Action. Local verification uses fakes.
- Commits are small and phase-scoped; every commit message states the phase
  (e.g. `phase1: markdown section parser`).
- Fix PRs created by the Action: branch `dochealer/fix-pr-<n>`, label `dochealer`,
  and the Action must skip any PR bearing that label or branch prefix (loop safety).
- Secrets only via Action inputs/env at runtime; never written to disk, logs, or prompts.

## 6. What the AI Should NOT Do

- Don't build ahead of the current phase in Phases.md; don't skip its "done when" gate.
- Don't rewrite files wholesale when a targeted edit suffices — mirrors the product's own
  philosophy of minimal, targeted corrections.
- Don't invent test results — run the tests, paste real output.
- Don't add features outside PRD non-goals (multi-language parsing, auto-merge, SaaS)
  without an explicit user decision recorded in Memory.md.
- Don't touch `.dochealer/` index format, prompts, or confidence thresholds without
  updating the relevant doc file and Memory.md in the same commit.

## 7. Testing Rules

- Every parser/filter/graph module gets unit tests in the same phase it's built — a phase
  is not done with failing or missing tests.
- LLM-dependent logic is tested with a `FakeLLMClient` returning canned JSON; GitHub
  side effects with a `FakeGitHub`. No network in tests, ever.
- The fixture repo in `tests/fixtures/sample_repo/` is the ground truth for e2e tests;
  changes to it must keep at least: 1 true-stale case, 1 accurate-docs case, 1
  meaningless-change case.
