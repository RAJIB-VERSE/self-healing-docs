"""Provider-agnostic LLM client (Rules.md §3: all LLM calls go through here).

One entrypoint — chat_json(system, user, schema) — returning a validated pydantic
model. JSON parse/validation failures retry once, then raise LLMUnavailable so the
caller can degrade to "flag for review" instead of crashing (Rules.md §4).
"""
from __future__ import annotations

import json
import logging
from typing import Protocol, TypeVar

from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-6",
    "github": "openai/gpt-4o",  # GitHub Models: free tier, OpenAI-compatible
}
GITHUB_MODELS_BASE_URL = "https://models.github.ai/inference"
_TIMEOUT_S = 60.0


class LLMUnavailable(Exception):
    """Raised when the LLM cannot produce a valid response; caller degrades gracefully."""


class LLMClient(Protocol):
    """Injected everywhere; FakeLLMClient in tests (Rules.md §7)."""

    def chat_json(self, system: str, user: str, schema: type[T]) -> T: ...


def _extract_json(text: str) -> str:
    """Tolerate markdown-fenced JSON from providers without strict JSON mode."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()


class _BaseClient:
    def __init__(self, model: str) -> None:
        self._model = model
        self.calls_made = 0  # surfaced in the PR comment footer (Design.md §2)

    def _complete(self, system: str, user: str) -> str:  # pragma: no cover - provider-specific
        raise NotImplementedError

    def chat_json(self, system: str, user: str, schema: type[T]) -> T:
        prompt = (
            f"{user}\n\nRespond with ONLY a JSON object matching this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=None)}"
        )
        last_error: Exception | None = None
        for attempt in (1, 2):  # one retry per Rules.md §3
            try:
                self.calls_made += 1
                raw = self._complete(system, prompt)
                return schema.model_validate(json.loads(_extract_json(raw)))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                log.warning("[llm] attempt %d: invalid JSON response (%s)", attempt, exc)
            except Exception as exc:  # noqa: BLE001 — SDK/network errors vary by provider
                last_error = exc
                log.warning("[llm] attempt %d: request failed (%s)", attempt, exc)
        raise LLMUnavailable(str(last_error))


class OpenAIClient(_BaseClient):
    """OpenAI, or any OpenAI-compatible endpoint (e.g. GitHub Models) via base_url."""

    def __init__(self, api_key: str, model: str = "", base_url: str = "") -> None:
        super().__init__(model or DEFAULT_MODELS["openai"])
        from openai import OpenAI  # deferred: keep importable offline

        self._client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=_TIMEOUT_S)

    def _complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return response.choices[0].message.content or ""


class AnthropicClient(_BaseClient):
    def __init__(self, api_key: str, model: str = "") -> None:
        super().__init__(model or DEFAULT_MODELS["anthropic"])
        from anthropic import Anthropic  # deferred: keep importable offline

        self._client = Anthropic(api_key=api_key, timeout=_TIMEOUT_S)

    def _complete(self, system: str, user: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in response.content if b.type == "text")


def make_client(provider: str, api_key: str, model: str = "") -> LLMClient:
    if provider == "anthropic":
        return AnthropicClient(api_key, model)
    if provider == "github":
        return OpenAIClient(
            api_key, model or DEFAULT_MODELS["github"], base_url=GITHUB_MODELS_BASE_URL
        )
    return OpenAIClient(api_key, model)
