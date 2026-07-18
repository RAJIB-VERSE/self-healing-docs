"""Shared fixtures: parsed fixture repo + fakes for LLM/embeddings."""
from __future__ import annotations

from pathlib import Path

import pytest

from dochealer.config import Settings

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "sample_repo"


@pytest.fixture
def settings() -> Settings:
    return Settings(repo_root=FIXTURE_REPO, docs_path="docs", include_readme=True)


class FakeEmbedder:
    """Deterministic embeddings: direction encodes presence of keyword tokens."""

    def __init__(self, vocabulary: list[str] | None = None) -> None:
        self.vocabulary = vocabulary or ["user", "retry", "timeout", "delete", "settings"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            lowered = text.lower()
            vec = [float(lowered.count(word)) for word in self.vocabulary]
            out.append(vec if any(vec) else [0.001] * len(self.vocabulary))
        return out


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    return FakeEmbedder()
