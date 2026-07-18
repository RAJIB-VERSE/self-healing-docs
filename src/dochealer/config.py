"""Runtime configuration for dochealer.

All Action inputs land here. Env vars use the DOCHEALER_ prefix (Design.md §6);
the GitHub Action maps its inputs onto these vars in action.yml.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Bump when CodeChunk/DocSection ID formats or parser semantics change (Rules.md §2).
INDEX_VERSION = 1

INDEX_DIR = ".dochealer"
INDEX_FILE = "index.json"
CHROMA_DIR = "chroma"

FIX_BRANCH_PREFIX = "dochealer/fix-pr-"
FIX_LABEL = "dochealer"
SUMMARY_MARKER = "<!-- dochealer-summary -->"


@dataclass
class Settings:
    repo_root: Path
    docs_path: str = "docs"
    include_readme: bool = True
    llm_provider: str = "openai"  # "openai" | "anthropic"
    llm_api_key: str = ""
    llm_model: str = ""  # empty -> provider default
    embedding_model: str = "text-embedding-3-small"
    confidence_threshold: float = 0.8
    mode: str = "fix"  # "fix" | "flag-only"
    similarity_threshold: float = 0.78  # embedding link cutoff
    # Hard caps per Rules.md §3
    max_verifications: int = 20
    max_corrections: int = 10
    max_code_context_chars: int = 24_000  # ~8k tokens
    github_token: str = ""
    github_repo: str = ""  # "owner/name"
    pr_number: int = 0

    code_globs: tuple[str, ...] = ("**/*.py",)
    ignore_dirs: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {".git", ".dochealer", "node_modules", ".venv", "venv", "__pycache__",
             "build", "dist", ".github"}
        )
    )

    @property
    def index_path(self) -> Path:
        return self.repo_root / INDEX_DIR / INDEX_FILE

    @property
    def chroma_path(self) -> Path:
        return self.repo_root / INDEX_DIR / CHROMA_DIR

    @classmethod
    def from_env(cls, repo_root: Path | None = None) -> Settings:
        env = os.environ

        def flag(name: str, default: bool) -> bool:
            raw = env.get(name)
            return default if raw is None else raw.strip().lower() in {"1", "true", "yes"}

        return cls(
            repo_root=repo_root or Path(env.get("GITHUB_WORKSPACE", ".")).resolve(),
            docs_path=env.get("DOCHEALER_DOCS_PATH", "docs"),
            include_readme=flag("DOCHEALER_INCLUDE_README", True),
            llm_provider=env.get("DOCHEALER_LLM_PROVIDER", "openai"),
            llm_api_key=env.get("DOCHEALER_LLM_API_KEY", ""),
            llm_model=env.get("DOCHEALER_LLM_MODEL", ""),
            confidence_threshold=float(env.get("DOCHEALER_CONFIDENCE_THRESHOLD", "0.8")),
            mode=env.get("DOCHEALER_MODE", "fix"),
            github_token=env.get("DOCHEALER_GITHUB_TOKEN", env.get("GITHUB_TOKEN", "")),
            github_repo=env.get("GITHUB_REPOSITORY", ""),
            pr_number=int(env.get("DOCHEALER_PR_NUMBER", "0") or 0),
        )
