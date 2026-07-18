"""Embedding support for the linker: OpenAI embeddings persisted in ChromaDB.

Optional at runtime — when no API key is configured, the linker runs in
heuristic-only mode (Phases.md Phase 1.4). Chroma data is a rebuildable cache
under .dochealer/chroma/ and is gitignored.
"""
from __future__ import annotations

import logging
from typing import Protocol

from dochealer.config import Settings
from dochealer.models import CodeChunk, DocSection

log = logging.getLogger(__name__)


class EmbeddingBackend(Protocol):
    """Injected by callers; FakeEmbedder in tests (Rules.md §7)."""

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        from openai import OpenAI  # deferred import: keep module importable offline

        self._client = OpenAI(api_key=api_key)
        self._model = model

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in response.data]


def _chunk_text(chunk: CodeChunk) -> str:
    return f"{chunk.kind} {chunk.qualname}\n{chunk.signature}\n{chunk.docstring}"


def _section_text(section: DocSection) -> str:
    return f"{section.title}\n{section.content[:2000]}"


def similarity_links(
    chunks: list[CodeChunk],
    sections: list[DocSection],
    backend: EmbeddingBackend,
    settings: Settings,
) -> list[tuple[str, str, float]]:
    """Return (doc_id, chunk_id, score) pairs above the similarity threshold.

    Embeddings are computed in one batch per side and compared in-process with
    Chroma's cosine math replicated locally — for MVP scale (hundreds of items)
    a brute-force loop is simpler and has no persistence edge cases. Chroma
    persistence is layered on in the Action for caching between runs.
    """
    if not chunks or not sections:
        return []
    try:
        chunk_vecs = backend.embed([_chunk_text(c) for c in chunks])
        section_vecs = backend.embed([_section_text(s) for s in sections])
    except Exception as exc:  # noqa: BLE001 — degrade per Rules.md §4
        log.warning("[index] embedding failed (%s); heuristic-only links", exc)
        return []

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    out: list[tuple[str, str, float]] = []
    for section, svec in zip(sections, section_vecs, strict=True):
        for chunk, cvec in zip(chunks, chunk_vecs, strict=True):
            score = cosine(svec, cvec)
            if score >= settings.similarity_threshold:
                out.append((section.id, chunk.id, score))
    return out
