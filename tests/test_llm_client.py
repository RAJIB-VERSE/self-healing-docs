from dochealer.llm.client import (
    DEFAULT_MODELS,
    GITHUB_MODELS_BASE_URL,
    _extract_json,
)


def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == '{"a": 1}'


def test_extract_json_fenced():
    assert _extract_json('```json\n{"a": 1}\n```') == '{"a": 1}'


def test_extract_json_fenced_no_lang():
    assert _extract_json('```\n{"a": 1}\n```') == '{"a": 1}'


def test_github_provider_defaults():
    assert DEFAULT_MODELS["github"] == "openai/gpt-4o"
    assert GITHUB_MODELS_BASE_URL == "https://models.github.ai/inference"
