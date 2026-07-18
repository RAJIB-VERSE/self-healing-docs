"""LLM verification of suspect doc sections (Phases.md Phase 2.4).

For each (changed chunk, linked section) pair: send old code, new code, and the
doc text; get back a JSON verdict. Caps and graceful degradation per Rules.md §3–4.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from dochealer.config import Settings
from dochealer.llm.client import LLMClient, LLMUnavailable
from dochealer.models import ChangedChunk, DocSection, LinkGraph, StalenessVerdict

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a meticulous technical-documentation reviewer. You are shown a code "
    "change (old and new versions) and a documentation section that references that "
    "code. Decide whether the documentation is still accurate AFTER the change. "
    "Only mark it stale if a specific statement in the docs is now wrong or "
    "misleading; style or omissions are not staleness. Be precise about what is wrong."
)


class _VerdictPayload(BaseModel):
    stale: bool
    diagnosis: str = Field(
        default="", description="what specifically is now wrong; empty if accurate"
    )
    confidence: float = Field(ge=0.0, le=1.0)


def find_suspects(
    graph: LinkGraph, changes: list[ChangedChunk]
) -> list[tuple[DocSection, list[ChangedChunk]]]:
    """Map meaningful changes to the doc sections they may invalidate."""
    by_section: dict[str, tuple[DocSection, list[ChangedChunk]]] = {}
    for change in changes:
        for section in graph.sections_for_chunk(change.chunk_id):
            entry = by_section.setdefault(section.id, (section, []))
            entry[1].append(change)
    return list(by_section.values())


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n# ...clipped..."


def _prompt(section: DocSection, changes: list[ChangedChunk], settings: Settings) -> str:
    budget = settings.max_code_context_chars // max(len(changes), 1)
    parts = [f"## Documentation section: {section.title}\n\n{section.content}\n"]
    for ch in changes:
        parts.append(f"\n## Code change ({ch.change_kind}): {ch.chunk_id}")
        if ch.old_source:
            parts.append(f"\n### OLD code\n```python\n{_clip(ch.old_source, budget)}\n```")
        if ch.new_source:
            parts.append(f"\n### NEW code\n```python\n{_clip(ch.new_source, budget)}\n```")
        if ch.change_kind == "removed":
            parts.append("\n(The code above was REMOVED entirely.)")
    parts.append(
        "\nIs the documentation section still accurate after these changes? "
        "If stale, state exactly which claim is wrong and what the truth now is."
    )
    return "\n".join(parts)


def verify_suspects(
    suspects: list[tuple[DocSection, list[ChangedChunk]]],
    client: LLMClient,
    settings: Settings,
) -> tuple[list[StalenessVerdict], list[str]]:
    """Return (verdicts, skipped_section_ids). Never raises (Rules.md §4)."""
    verdicts: list[StalenessVerdict] = []
    skipped: list[str] = []
    for i, (section, changes) in enumerate(suspects):
        if i >= settings.max_verifications:
            skipped.append(section.id)
            continue
        try:
            payload = client.chat_json(
                SYSTEM_PROMPT, _prompt(section, changes, settings), _VerdictPayload
            )
            verdicts.append(StalenessVerdict(
                section_id=section.id, stale=payload.stale,
                diagnosis=payload.diagnosis, confidence=payload.confidence,
            ))
            log.info("[detect] %s → %s (conf %.2f)",
                     section.id, "STALE" if payload.stale else "accurate", payload.confidence)
        except LLMUnavailable as exc:
            log.warning("[detect] verification unavailable for %s: %s", section.id, exc)
            skipped.append(section.id)
    if skipped:
        log.info("[detect] %d sections skipped (cap/errors)", len(skipped))
    return verdicts, skipped
