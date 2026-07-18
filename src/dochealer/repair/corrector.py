"""Generate targeted doc corrections for confirmed-stale sections (Phase 3.1).

Prompt discipline: rewrite ONLY the stale parts, preserve style/structure, keep
accurate content verbatim. Returns the full replacement section plus a summary
and confidence.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from dochealer.config import Settings
from dochealer.llm.client import LLMClient, LLMUnavailable
from dochealer.models import ChangedChunk, Correction, DocSection, StalenessVerdict

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a surgical technical writer. You fix ONLY the inaccurate parts of a "
    "documentation section, given the new code and a diagnosis of what is stale. "
    "Hard rules: (1) change nothing that is still accurate — reproduce it "
    "character-for-character; (2) preserve the original heading, tone, formatting, "
    "and markdown structure; (3) never add new sections or commentary; "
    "(4) if part of the fix requires product knowledge you don't have, insert "
    "'<!-- TODO(dochealer): ... -->' rather than guessing."
)


class _CorrectionPayload(BaseModel):
    new_content: str = Field(description="full replacement markdown for the section")
    summary: str = Field(description="one line: what changed and why")
    confidence: float = Field(ge=0.0, le=1.0)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n# ...clipped..."


def _prompt(
    section: DocSection,
    verdict: StalenessVerdict,
    changes: list[ChangedChunk],
    settings: Settings,
) -> str:
    budget = settings.max_code_context_chars // max(len(changes), 1)
    parts = [
        f"## Current documentation section ({section.title})\n\n{section.content}",
        f"\n## Staleness diagnosis\n{verdict.diagnosis}",
    ]
    for ch in changes:
        parts.append(f"\n## NEW code ({ch.chunk_id})")
        source = ch.new_source or "(removed entirely)"
        parts.append(f"```python\n{_clip(source, budget)}\n```")
    parts.append(
        "\nProduce the corrected section. Remember: minimal edits, preserve "
        "everything that is still true, keep the heading line unchanged unless "
        "the heading itself is stale."
    )
    return "\n".join(parts)


def generate_correction(
    section: DocSection,
    verdict: StalenessVerdict,
    changes: list[ChangedChunk],
    client: LLMClient,
    settings: Settings,
) -> Correction | None:
    """One targeted rewrite; None when the LLM is unavailable (caller flags instead)."""
    try:
        payload = client.chat_json(
            SYSTEM_PROMPT, _prompt(section, verdict, changes, settings), _CorrectionPayload
        )
    except LLMUnavailable as exc:
        log.warning("[repair] correction unavailable for %s: %s", section.id, exc)
        return None
    todos = [line for line in payload.new_content.splitlines() if "TODO(dochealer)" in line]
    return Correction(
        section_id=section.id,
        new_content=payload.new_content,
        summary=payload.summary,
        confidence=payload.confidence,
        todo_markers=todos,
    )
