"""Core data models passed between pipeline stages.

Per Rules.md §2: these models are the only data crossing module boundaries.
ID formats are stable contracts — bump INDEX_VERSION in config.py if they change.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

ChunkKind = Literal["function", "class", "method", "config", "cli"]
ChangeKind = Literal["modified", "added", "removed"]
LinkSource = Literal["heuristic", "embedding"]


def slugify(text: str) -> str:
    """Lowercase, alphanumerics and hyphens only — GitHub-anchor style."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[\s_]+", "-", text)


class CodeChunk(BaseModel):
    """A semantic unit of code (function/class/method/config/CLI command)."""

    path: str  # repo-relative, posix separators
    kind: ChunkKind
    name: str
    qualname: str  # e.g. "MyClass.my_method"
    signature: str  # e.g. "def get_user(user_id: int, *, active: bool = True) -> User"
    docstring: str = ""
    source: str
    lineno: int
    end_lineno: int

    @property
    def id(self) -> str:
        return f"{self.path}::{self.qualname}"


class DocSection(BaseModel):
    """A markdown section delimited by its heading."""

    path: str
    heading_path: tuple[str, ...]  # ("Configuration", "Environment Variables")
    level: int  # heading level of the section's own heading (1-6)
    content: str  # raw markdown including the heading line
    code_refs: list[str] = Field(default_factory=list)  # identifiers mentioned
    lineno: int
    end_lineno: int

    @property
    def id(self) -> str:
        return f"{self.path}#{slugify(' '.join(self.heading_path))}"

    @property
    def title(self) -> str:
        return " › ".join(self.heading_path)


class Link(BaseModel):
    doc_id: str
    chunk_id: str
    source: LinkSource
    score: float = 1.0  # 1.0 for heuristic; cosine similarity for embedding


class LinkGraph(BaseModel):
    """The persisted code-to-docs index."""

    version: int
    chunks: list[CodeChunk]
    sections: list[DocSection]
    links: list[Link]

    def sections_for_chunk(self, chunk_id: str) -> list[DocSection]:
        doc_ids = {ln.doc_id for ln in self.links if ln.chunk_id == chunk_id}
        return [s for s in self.sections if s.id in doc_ids]

    def chunk_by_id(self, chunk_id: str) -> CodeChunk | None:
        return next((c for c in self.chunks if c.id == chunk_id), None)

    def section_by_id(self, doc_id: str) -> DocSection | None:
        return next((s for s in self.sections if s.id == doc_id), None)


class ChangedChunk(BaseModel):
    """A code chunk affected by the PR diff."""

    chunk_id: str
    change_kind: ChangeKind
    old_source: str = ""
    new_source: str = ""
    old_signature: str = ""
    new_signature: str = ""


class StalenessVerdict(BaseModel):
    """LLM verification result for one suspect doc section."""

    section_id: str
    stale: bool
    diagnosis: str = ""  # what specifically is wrong, empty if accurate
    confidence: float = 0.0  # 0..1


class Correction(BaseModel):
    """A generated doc fix for one stale section."""

    section_id: str
    new_content: str
    summary: str  # one-line description of what changed and why
    validated: bool = False
    confidence: float = 0.0  # min(correction confidence, validation confidence)
    todo_markers: list[str] = Field(default_factory=list)


class RunReport(BaseModel):
    """Final result of one Action run — feeds comments and outputs."""

    analyzed_changes: int = 0
    verified_ok: list[str] = Field(default_factory=list)  # section ids
    fixed: list[Correction] = Field(default_factory=list)
    flagged: list[StalenessVerdict] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)  # section ids skipped (caps/errors)
    notes: list[str] = Field(default_factory=list)  # warnings for the summary comment
    fix_pr_url: str = ""
