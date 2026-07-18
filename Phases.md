# Phases — Build Plan

Each phase ends with a **Done when** gate: code + tests passing + Memory.md updated.
Do not start a phase until the previous gate is met.

## Phase 0 — Scaffold ✅ (gate: repo skeleton committed)
- git init, `.gitignore`, `pyproject.toml`, package layout under `src/dochealer/`,
  empty test dirs, planning docs (this file set) committed.
- **Done when**: `pip install -e .` works and `pytest` collects (0 tests ok).

## Phase 1 — Code-to-Docs Mapping (spec days 1–4)
1. `models.py` — all pipeline dataclasses.
2. `indexing/code_parser.py` — Python AST walk → `CodeChunk`s (functions, classes,
   methods; capture signature, docstring, source, line spans; stable IDs).
3. `indexing/doc_parser.py` — markdown → `DocSection`s by heading; heading paths;
   extract code refs (backticked identifiers, `--flags`, UPPER_SNAKE config keys,
   dotted/called names in prose).
4. `indexing/linker.py` — heuristic links (section mentions chunk name); then
   `indexing/embedder.py` (OpenAI + Chroma) and similarity links above threshold.
   Embedder is optional at runtime: no API key → heuristic-only mode.
5. Index persistence: `.dochealer/index.json` (versioned), Chroma as rebuildable cache.
- **Done when**: unit tests for both parsers + linker pass on the fixture repo;
  `dochealer index` CLI builds an index.json for the fixture.

## Phase 2 — Change Detection (spec days 4–7)
1. `detection/diff_parser.py` — `git diff base...head -U0` → changed line ranges per file
   → intersect with chunk line spans → `ChangedChunk`s (with old/new source).
2. `detection/change_filter.py` — drop: comment/whitespace-only edits, docstring-only
   edits, test files, private helpers with no links. Keep: signature changes, default
   value changes, added/removed public chunks, body changes to linked chunks.
3. Suspect lookup: `LinkGraph.affected_sections(changed_chunks)`.
4. `detection/staleness.py` — LLM verification (old code, new code, doc text → JSON
   verdict: `stale`, `diagnosis`, `confidence`). Cap + graceful degradation per Rules.md.
- **Done when**: diff/filter unit tests pass; e2e test with FakeLLM shows the fixture's
  true-stale case caught and the meaningless-change case filtered before any LLM call.

## Phase 3 — Doc Repair Engine (spec days 7–10)
1. `repair/corrector.py` — targeted rewrite: prompt includes doc section, new code,
   diagnosis; instructions to change only stale parts, preserve style; returns full
   replacement section + list of changed spans + confidence.
2. `repair/validator.py` — second LLM pass: accuracy vs. new code, preservation of
   still-correct content, style consistency → pass/fail + confidence.
3. Confidence routing in `main.py`: `min(confidences) ≥ threshold` → auto-fix list;
   else → flag list with TODO-marked draft.
- **Done when**: with FakeLLM, pipeline produces a Correction for the stale fixture
  section, and a low-confidence canned response routes to the flag path.

## Phase 4 — GitHub Action Packaging (spec days 10–12)
1. `github/pr_writer.py` — branch `dochealer/fix-pr-<n>`, apply corrections to doc files,
   commit, open PR (labeled `dochealer`), body describing each fix and why.
2. `github/commenter.py` — upserted summary comment (hidden marker) + review-flag
   comment with section links and diagnoses.
3. `report.py` — RunReport → comment markdown + `report-json` output.
4. `action.yml` (inputs/outputs per PRD §8), `Dockerfile`, `main.py` wiring, loop-safety
   guard, `GITHUB_OUTPUT` writing.
5. `.github/workflows/ci.yml` (ruff + pytest) and `self-test.yml` (dogfood run).
- **Done when**: `docker build` succeeds; e2e test with FakeGitHub asserts branch,
  PR body, and comment contents; CI workflow green locally via `pytest`.

## Phase 5 — Real-Repo Testing (spec days 12–13)
1. Fork a well-documented Python project (target: FastAPI or Pydantic), install the Action.
2. Inject 6–10 deliberate doc-invalidating changes (rename param, change default, remove
   feature, add feature, pure refactor as control, comment-only as control).
3. Record TP / FP / FN and correction quality into `docs/evaluation.md`; tune
   thresholds; report numbers in README.
- **Done when**: metrics table exists with real numbers meeting (or honestly missing)
  PRD §6 targets.

## Phase 6 — Portfolio Polish (spec days 13–14)
1. README: problem story, demo GIF, install snippet, metrics table, architecture diagram.
2. Marketplace publishing: `branding` in action.yml, tagged release `v1`.
3. Demo video (< 3 min): push change → Action runs → summary comment → fix PR.
- **Done when**: Action installable from marketplace; README complete; video linked.
