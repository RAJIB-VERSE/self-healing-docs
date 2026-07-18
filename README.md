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

```yaml
# .github/workflows/dochealer.yml
name: Doc check
on:
  pull_request:
    paths: ["**/*.py"]

permissions:
  contents: write
  pull-requests: write

jobs:
  dochealer:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: <owner>/self-healing-docs@v1
        with:
          llm-api-key: ${{ secrets.OPENAI_API_KEY }}
          docs-path: "docs"
```

### Inputs

| Input | Default | Description |
|---|---|---|
| `llm-api-key` | *(required)* | OpenAI or Anthropic API key |
| `llm-provider` | `openai` | `openai` or `anthropic` |
| `llm-model` | provider default | Override model (`gpt-4o` / `claude-sonnet-4-6`) |
| `docs-path` | `docs` | Documentation directory |
| `include-readme` | `true` | Also check `README.md` |
| `confidence-threshold` | `0.8` | Minimum confidence for auto-fix PRs |
| `mode` | `fix` | `fix` (open PRs) or `flag-only` (comments only) |
| `github-token` | `${{ github.token }}` | Token for PRs and comments |

### Outputs

`stale-count` · `fixed-count` · `flagged-count` · `fix-pr-url` · `report-json`

## Local usage

```bash
pip install -e .
dochealer index --repo /path/to/repo --docs-path docs   # build the index
```

## Design guarantees

- **Never fails your PR** — findings arrive as comments, infra errors degrade
  gracefully. Exit code is always 0.
- **Filter before LLM** — PRs with no doc impact cost $0 in API calls.
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
