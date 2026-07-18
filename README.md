# 🩺 Self-Healing Docs

**Docs that fix themselves when your code changes.**

A GitHub Action that detects when a pull request makes your documentation
inaccurate, pinpoints the exact stale sections, and either opens a PR with
corrected docs or flags them for human review.

```
your PR  ──►  🩺 dochealer  ──►  ✅ 3 verified · 🩹 1 auto-fixed → #42 · ⚠️ 2 flagged
```

## Why

Documentation goes stale the moment code changes — a renamed parameter, a new
default, a removed feature — and nobody notices until a user does. dochealer
lives in your CI pipeline and catches the drift on every PR.

## How it works

1. **Index** — parses your Python code (AST) and markdown docs into semantic
   chunks, then links them with name-mention heuristics + embedding similarity.
   The index persists at `.dochealer/index.json`.
2. **Detect** — parses the PR diff into changed code chunks, filters out
   non-meaningful changes (comments, whitespace, docstrings, tests, private
   helpers) *before* spending a single LLM token, then verifies each suspect
   doc section with an LLM against the old + new code.
3. **Repair** — generates a targeted rewrite of only the stale parts, runs a
   second LLM validation pass (accuracy / preservation / style), and routes by
   confidence: high → auto-fix PR, low → review flag.
4. **Report** — posts one upserted summary comment on the PR with links to
   everything.

## Install

**Free option (no API key needed)** — uses the [GitHub Models](https://github.blog/ai-and-ml/llms/solving-the-inference-problem-for-open-source-ai-projects-with-github-models/)
free tier via the workflow's built-in token:

```yaml
# .github/workflows/dochealer.yml
name: Doc check
on:
  pull_request:
    paths: ["**/*.py"]

permissions:
  contents: write
  pull-requests: write
  models: read          # unlocks the free GitHub Models tier

jobs:
  dochealer:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: RAJIB-VERSE/self-healing-docs@v1
        with:
          llm-api-key: ${{ github.token }}
          llm-provider: "github"
```

With a paid OpenAI or Anthropic key (higher rate limits, better for large PRs):

```yaml
      - uses: RAJIB-VERSE/self-healing-docs@v1
        with:
          llm-api-key: ${{ secrets.OPENAI_API_KEY }}
          docs-path: "docs"
```

### Inputs

| Input | Default | Description |
|---|---|---|
| `llm-api-key` | *(required)* | API key — `${{ github.token }}` for the free tier, or an OpenAI/Anthropic key |
| `llm-provider` | `openai` | `openai`, `anthropic`, or `github` (free GitHub Models tier) |
| `llm-model` | provider default | Override model (`gpt-4o` / `claude-sonnet-4-6` / `openai/gpt-4o-mini`) |
| `docs-path` | `docs` | Documentation directory |
| `include-readme` | `true` | Also check `README.md` |
| `confidence-threshold` | `0.8` | Minimum confidence for auto-fix PRs |
| `mode` | `fix` | `fix` (open PRs) or `flag-only` (comments only) |
| `github-token` | `${{ github.token }}` | Token for PRs and comments |

### Outputs

`stale-count` · `fixed-count` · `flagged-count` · `fix-pr-url` · `report-json`

## Local usage

Run the same pipeline on your machine before pushing — no GitHub Action needed:

```bash
pip install -e .

# build the code-to-docs index
dochealer index --repo . --docs-path docs

# check your branch's changes against main (uses the free GitHub Models tier)
export DOCHEALER_LLM_PROVIDER=github
export DOCHEALER_LLM_API_KEY=$(gh auth token)
dochealer check --base-ref main

# write high-confidence fixes straight into your working tree
dochealer check --base-ref main --apply
```

`check` exits `1` when staleness is found, so it drops straight into a
pre-push hook or any CI gate.

## Design guarantees

- **Never fails your PR** — findings arrive as comments, infra errors degrade
  gracefully. Exit code is always 0 (the local `check` command *does* signal via
  exit code, by design).
- **Filter before LLM** — PRs with no doc impact cost $0 in API calls; every
  run's comment footer shows exactly how many LLM calls were made.
- **Constants tracked too** — module-level `UPPER_SNAKE` values (default
  timeouts, retry counts…) are indexed, so a changed default that docs quote
  gets caught.
- **Loop-safe** — dochealer skips its own fix PRs (branch prefix + label).
- **Hard caps** — max 20 verifications and 10 corrections per run; overflow is
  flagged, never silently dropped.

## Evaluation

Accuracy numbers from testing against a real repository land here after the
evaluation phase (see `Phases.md` Phase 5).

| Metric | Target | Measured |
|---|---|---|
| Staleness recall | ≥ 80% | _pending_ |
| Precision | ≥ 75% | _pending_ |
| Correction quality | ≥ 90% | _pending_ |

## Development

```bash
pip install -e ".[dev]"
ruff check src tests && pytest -q
```

Project planning lives in [PRD.md](PRD.md), [Architecture.md](Architecture.md),
[Rules.md](Rules.md), [Phases.md](Phases.md), [Design.md](Design.md); progress
log in [Memory.md](Memory.md).

## License

MIT

## Acknowledgements

