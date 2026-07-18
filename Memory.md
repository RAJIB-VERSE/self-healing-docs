# Memory — Progress Log

Purpose: keep any AI session up to date on project state without re-reading the
whole codebase. Update at every phase gate and for every decision that changes
Rules/Architecture (Rules.md §6).

## Current state

- **Phase**: 4 complete (code + tests). Remaining: Docker build verification (no
  Docker on this machine — CI's `docker` job covers it), then Phase 5 (real-repo
  eval) and Phase 6 (marketplace polish), both of which need a GitHub remote.
- **Tests**: 60 passing (`pytest -q`), ruff clean
- **Commits**: phase0 → phase1 → phase2 → phase3 → phase4 (one commit per gate)
- **Env**: Windows, git-bash; venv at `.venv/` (`.venv/Scripts/python`); Python 3.14
  local (project targets 3.11+ — CI/Docker pin 3.11). **No Docker locally.**

## Decisions made (beyond the planning docs)

0. **LLM provider = GitHub Models free tier (2026-07-18, user decision).** User has no
   paid OpenAI/Anthropic key. Added third provider `github`: OpenAI-compatible endpoint
   `https://models.github.ai/inference`, auth = GitHub token (in Actions: the built-in
   `github.token` + `models: read` job permission — zero secrets). Default model
   `openai/gpt-4o`; dogfood workflow uses `openai/gpt-4o-mini` (15 req/min vs 10).
   Free-tier limits: ~8k tokens in / 4k out per request, 50–150 req/day — fine for
   dogfood + Phase 5 eval, documented as "paid key for large PRs" in README.
   GitHub account: **RAJIB-VERSE** (gh CLI authenticated on this machine).

1. **Kickoff defaults**: user said "continue with the build" without answering open
   questions → Python 3.11+, OpenAI primary, Anthropic behind `llm-provider` input.
2. **Embedding comparison is brute-force in-process** (embedder.py); ChromaDB is a
   between-run cache only, deferred until real-repo scale demands it. `chromadb` is
   still declared in pyproject deps.
3. **Module-level constants (e.g. `DEFAULT_TIMEOUT`) are NOT extracted as chunks.**
   The fixture's "Timeouts" section therefore has no links — revisit in Phase 5 if
   eval shows missed staleness.
4. **`(intro)` pseudo-heading** for pre-first-heading markdown; level 0.
5. **LLM JSON strategy**: prompt embeds the pydantic JSON schema; OpenAI uses
   `response_format=json_object`, Anthropic parses fenced output; 1 retry then
   `LLMUnavailable` → caller degrades to flag/skip.
6. **FakeLLMClient keys canned responses by prompt substring** — pipeline tests
   register markers: "Is the documentation section still accurate" (verifier),
   "Staleness diagnosis" (corrector), "Run the three checks" (validator).
7. **Auto-fix requires**: validation passed AND min(verify, correction, validation
   confidences) ≥ threshold AND no TODO markers. Anything else → flagged.
8. **Section splicing is bottom-up per file** (pr_writer.apply_corrections_to_files)
   so line numbers stay valid; nested-section overlap is not handled (a parent and
   child section both corrected in one run would conflict — corrections come per
   section-id so this hasn't occurred; guard if Phase 5 hits it).
9. **entrypoint.sh reads the event payload with python one-liners** (no jq dep).

## File map

- `src/dochealer/models.py` — pydantic models; `config.py` — Settings, caps, markers
- `indexing/` — code_parser (AST), doc_parser (markdown+refs), embedder, linker
- `detection/` — diff_parser (git diff → ChangedChunks), change_filter
  (tokenize+AST normalization), staleness (LLM verify, caps)
- `repair/` — corrector (targeted rewrite + TODO capture), validator (quality gate)
- `llm/client.py` — OpenAIClient/AnthropicClient/make_client, LLMUnavailable
- `github/pr_writer.py` — GitHubBackend protocol, splicing, fix-PR flow
- `github/commenter.py` — LiveGitHub (PyGithub+git), is_own_pr loop guard
- `report.py` — summary comment (Design.md §2 format) + report_json
- `main.py` — build_index / run_pipeline / run_action / CLI (`index`, `run`)
- Action: `action.yml`, `Dockerfile`, `entrypoint.sh`; workflows: ci.yml, self-test.yml
- Tests: 60 across parsers, linker, diff, filter, staleness, repair, pipeline e2e

## Gotchas for future sessions

- `ast.unparse` renders defaults as `bool=False` (no spaces) — tests assert this.
- Test imports use `from conftest import ...` (no package-relative imports in tests/).
- Windows: `.venv/Scripts/python`; plain `python` is 3.14; `python3` broken.
- CLI smoke tests leave `tests/fixtures/sample_repo/.dochealer/` — delete, never commit.
- Ruff line limit 100 — long `Link(...)`/f-string lines need wrapping.

## Next up

1. Push to GitHub, confirm CI (incl. docker build) green.
2. Phase 5: fork target repo, inject 6–10 doc-invalidating changes, record
   TP/FP/FN + correction quality into docs/evaluation.md, tune thresholds.
3. Phase 6: README metrics + demo video + marketplace release `v1`.
