"""Build the code-to-docs LinkGraph.

Two linking passes (Phases.md Phase 1.4):
1. Heuristic: a doc section that mentions a chunk's name/qualname links to it.
2. Embedding: cosine similarity above threshold (optional, needs an embedder).

The graph persists as versioned JSON at .dochealer/index.json (Architecture.md §5.1).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from dochealer.config import INDEX_VERSION, Settings
from dochealer.indexing.embedder import EmbeddingBackend, similarity_links
from dochealer.models import CodeChunk, DocSection, Link, LinkGraph

log = logging.getLogger(__name__)


def heuristic_links(chunks: list[CodeChunk], sections: list[DocSection]) -> list[Link]:
    """Link sections to chunks whose name or qualname they mention."""
    # name -> chunk ids (a name may appear in several files)
    by_name: dict[str, list[str]] = {}
    for chunk in chunks:
        by_name.setdefault(chunk.name, []).append(chunk.id)
        if chunk.qualname != chunk.name:
            by_name.setdefault(chunk.qualname, []).append(chunk.id)

    links: list[Link] = []
    for section in sections:
        matched: set[str] = set()
        for ref in section.code_refs:
            bare = ref.removesuffix("()")
            for chunk_id in by_name.get(bare, []):
                matched.add(chunk_id)
            # dotted refs like Settings.timeout -> also match class "Settings"
            if "." in bare:
                head = bare.split(".")[0]
                for chunk_id in by_name.get(head, []):
                    matched.add(chunk_id)
        links.extend(
            Link(doc_id=section.id, chunk_id=cid, source="heuristic")
            for cid in sorted(matched)
        )
    return links


def build_graph(
    chunks: list[CodeChunk],
    sections: list[DocSection],
    settings: Settings,
    embedder: EmbeddingBackend | None = None,
) -> LinkGraph:
    links = heuristic_links(chunks, sections)
    existing = {(ln.doc_id, ln.chunk_id) for ln in links}
    if embedder is not None:
        for doc_id, chunk_id, score in similarity_links(chunks, sections, embedder, settings):
            if (doc_id, chunk_id) not in existing:
                links.append(
                    Link(doc_id=doc_id, chunk_id=chunk_id, source="embedding", score=score)
                )
    log.info(
        "[index] graph: %d chunks, %d sections, %d links",
        len(chunks), len(sections), len(links),
    )
    return LinkGraph(version=INDEX_VERSION, chunks=chunks, sections=sections, links=links)


def save_graph(graph: LinkGraph, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")


def load_graph(path: Path) -> LinkGraph | None:
    """Load a persisted graph; None if missing or stale-versioned (forces rebuild)."""
    if not path.is_file():
        return None
    try:
        graph = LinkGraph.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("[index] invalid index at %s: %s — rebuilding", path, exc)
        return None
    if graph.version != INDEX_VERSION:
        log.info("[index] index version %d != %d — rebuilding", graph.version, INDEX_VERSION)
        return None
    return graph
