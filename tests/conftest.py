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


class FakeLLMClient:
    """Returns canned pydantic payloads keyed by substrings found in the prompt.

    responses: list of (needle, payload_dict). First needle found in the user
    prompt wins; payload is validated against the requested schema. A needle of
    "" acts as the default. Raises the configured exception when `fail` is set.
    """

    def __init__(self, responses, fail: Exception | None = None) -> None:
        self.responses = responses
        self.fail = fail
        self.calls: list[str] = []
        self.calls_made = 0

    def chat_json(self, system: str, user: str, schema):
        self.calls_made += 1
        self.calls.append(user)
        if self.fail is not None:
            raise self.fail
        for needle, payload in self.responses:
            if needle in user:
                return schema.model_validate(payload)
        raise AssertionError(f"FakeLLMClient: no canned response matches prompt:\n{user[:200]}")
