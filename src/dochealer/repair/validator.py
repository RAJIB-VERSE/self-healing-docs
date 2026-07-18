"""Second-pass validation of generated corrections — the quality gate (Phase 3.2).

Checks: accuracy vs. new code, preservation of still-correct content, style
consistency. Combined confidence = min(correction, validation); routing against
the threshold happens in main.py.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from dochealer.config import Settings
from dochealer.llm.client import LLMClient, LLMUnavailable
from dochealer.models import ChangedChunk, Correction, DocSection

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a documentation quality gate. Given the original section, a proposed "
    "corrected section, and the new code, verify three things: "
    "(1) ACCURACY — every claim in the corrected section is true of the new code; "
    "(2) PRESERVATION — content that was already correct was kept, not rewritten "
    "or dropped; (3) STYLE — tone and formatting match the original. "
    "Fail the correction if any check fails. Be strict: a wrong 'fix' is worse "
    "than no fix."
)


class _ValidationPayload(BaseModel):
    passes: bool
    problems: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "\n# ...clipped..."


def validate_correction(
    section: DocSection,
    correction: Correction,
    changes: list[ChangedChunk],
    client: LLMClient,
    settings: Settings,
) -> Correction:
    """Return the correction with validated/confidence updated. Never raises."""
    budget = settings.max_code_context_chars // max(len(changes), 1)
    code = "\n\n".join(
        f"### {ch.chunk_id}\n```python\n{_clip(ch.new_source or '(removed)', budget)}\n```"
        for ch in changes
    )
    prompt = (
        f"## Original section\n{section.content}\n\n"
        f"## Proposed corrected section\n{correction.new_content}\n\n"
        f"## New code\n{code}\n\n"
        "Run the three checks and return your verdict."
    )
    try:
        payload = client.chat_json(SYSTEM_PROMPT, prompt, _ValidationPayload)
    except LLMUnavailable as exc:
        log.warning("[repair] validation unavailable for %s: %s", section.id, exc)
        return correction.model_copy(update={"validated": False})
    if not payload.passes:
        log.info("[repair] validation FAILED for %s: %s", section.id, "; ".join(payload.problems))
    combined = min(correction.confidence, payload.confidence)
    return correction.model_copy(
        update={"validated": payload.passes, "confidence": combined}
    )
