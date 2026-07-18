"""Entrypoint: CLI for local use + Action orchestration.

Phase 1 ships the `index` command; `run` (the full pipeline) lands in Phase 4.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dochealer.config import Settings
from dochealer.indexing.code_parser import parse_repo
from dochealer.indexing.doc_parser import parse_docs
from dochealer.indexing.linker import build_graph, save_graph

log = logging.getLogger("dochealer")


def build_index(settings: Settings) -> None:
    """INDEX stage: parse code + docs, link, persist."""
    chunks = parse_repo(settings)
    sections = parse_docs(settings)
    embedder = None
    if settings.llm_api_key and settings.llm_provider == "openai":
        from dochealer.indexing.embedder import OpenAIEmbedder

        embedder = OpenAIEmbedder(settings.llm_api_key, settings.embedding_model)
    graph = build_graph(chunks, sections, settings, embedder=embedder)
    save_graph(graph, settings.index_path)
    log.info("[index] wrote %s", settings.index_path)


def cli(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(prog="dochealer")
    sub = parser.add_subparsers(dest="command", required=True)
    index_cmd = sub.add_parser("index", help="build the code-to-docs index")
    index_cmd.add_argument("--repo", default=".", help="repo root (default: cwd)")
    index_cmd.add_argument("--docs-path", default="docs")
    args = parser.parse_args(argv)

    if args.command == "index":
        settings = Settings.from_env(repo_root=Path(args.repo).resolve())
        settings.docs_path = args.docs_path
        build_index(settings)
    return 0


if __name__ == "__main__":
    sys.exit(cli())
