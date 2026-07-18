# PRD — Self-Healing Technical Documentation

## 1. Problem Statement

Documentation goes stale the moment code changes. Every engineering team experiences this:
a parameter gets renamed, a default value changes, a feature is removed — and the docs
silently keep describing the old world. Stale docs erode trust, waste onboarding time, and
generate support load. Nobody's job is "keep the docs in sync," so nobody does it.

## 2. Solution

A **GitHub Action** that runs on every pull request. It:

1. Maintains an index linking documentation sections to the code they describe.
2. Detects which code changes in a PR are *meaningful* (behavior/signature/config changes,
   not refactors or whitespace).
3. Identifies which doc sections are now *suspect*, and uses an LLM to verify whether each
   is actually stale (filtering false positives).
4. For confirmed staleness:
   - **High confidence** (renamed param, changed default, updated signature) → opens a
     companion PR with the corrected docs.
   - **Low confidence** (new feature, removed capability, semantic change) → comments on
     the original PR flagging the sections for human review.
5. Posts a summary comment on every PR it runs on:
   *"Doc Check: 3 sections verified accurate · 1 auto-fixed (PR #42) · 2 flagged for review."*

## 3. Target Users

| User | Need |
|---|---|
| **Open-source maintainers** | Keep README/docs accurate without manual policing of every PR |
| **Platform / DevEx teams** | Enforce doc hygiene across many internal repos via one reusable Action |
| **Small startup teams** | No dedicated docs person; automation is the only way docs stay correct |
| **Hiring managers / interviewers** (portfolio audience) | See a production-shaped AI system: embeddings, retrieval, LLM verification, CI/CD integration |

## 4. Core Features (MVP)

- **F1 — Code indexer**: AST-based extraction of functions, classes, CLI commands, and
  config schemas from Python codebases. Stable IDs (`path::qualname`).
- **F2 — Doc indexer**: Markdown sections split by heading, with heading paths and
  extracted code references (backticked identifiers, function names, config keys).
- **F3 — Link graph**: Doc section ↔ code chunk links via (a) exact name-mention
  heuristics and (b) embedding cosine similarity above a threshold. Persisted as JSON
  (`.dochealer/index.json`) in the repo.
- **F4 — Change detection**: Unified git diff → changed code chunks → filter to meaningful
  changes → suspect doc sections via the link graph.
- **F5 — LLM staleness verification**: old code + new code + doc section → verdict
  (accurate / stale + specific diagnosis + confidence).
- **F6 — Doc repair**: targeted rewrite of only the stale spans, style-preserving, with a
  second LLM validation pass as a quality gate.
- **F7 — GitHub Action packaging**: `action.yml` + Docker; inputs for API key, confidence
  threshold, docs path, mode; outputs for counts and PR URL.
- **F8 — PR workflow**: fix-PR creation, review comments, and the summary comment.

## 5. Non-Goals (MVP)

- Languages other than **Python** for code parsing (architecture allows adding parsers later).
- Doc formats other than **Markdown** (`.md`).
- Auto-merge of fix PRs (output supports it; default off; humans approve).
- Hosted dashboard / SaaS — this is a self-contained Action.
- Docstring rewriting inside code files (docs-directory + README only).

## 6. Success Metrics

Measured on a forked real-world repo (Phase 5 of the build) with deliberately injected
doc-invalidating changes:

- **Staleness recall** (true stale sections caught): target ≥ 80%
- **Precision** (flagged sections actually stale): target ≥ 75%
- **Correction quality** (auto-fixes judged correct by human review): target ≥ 90%
- **Runtime**: < 3 min on a typical PR (excluding first-run full indexing)
- **Cost**: < $0.10 per PR on default models

## 7. Key User Flows

### Flow A — PR with a meaningful code change
Dev pushes PR → Action runs → 1 doc section confirmed stale at high confidence →
Action opens fix PR, posts summary comment linking it → dev merges both.

### Flow B — PR with a complex change
Dev pushes PR → Action runs → staleness confirmed but low confidence →
Action comments on the PR listing the sections + diagnosis + TODO draft → human fixes docs.

### Flow C — PR with only refactors
Dev pushes PR → Action runs → changes filtered as non-meaningful → summary comment:
"No doc-impacting changes detected." Zero LLM verification calls (cost control).

## 8. Inputs / Outputs of the Action

**Inputs**: `llm-api-key` (required), `llm-provider` (`openai` | `anthropic`, default `openai`),
`docs-path` (default `docs/`), `include-readme` (default `true`), `confidence-threshold`
(default `0.8`), `mode` (`fix` | `flag-only`, default `fix`), `github-token` (default
`${{ github.token }}`).

**Outputs**: `stale-count`, `fixed-count`, `flagged-count`, `fix-pr-url`, `report-json`.

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM hallucinates a "fix" that's wrong | Validation pass (F6) + confidence gating + humans review PRs |
| Cost blowup on big PRs | Meaningful-change filter runs *before* any LLM call; hard cap on sections verified per run |
| Link graph misses implicit references | Dual linking (heuristic + embeddings); flagged-for-review path catches uncertainty |
| Secrets leakage in prompts | Only code diffs + doc text sent; no env/secret files ever included (enforced in Rules.md) |
| Infinite loop (fix PR triggers Action) | Action skips PRs authored by itself / labeled `dochealer` |
