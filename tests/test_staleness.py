from conftest import FakeLLMClient
from dochealer.detection.change_filter import filter_meaningful
from dochealer.detection.staleness import find_suspects, verify_suspects
from dochealer.indexing.code_parser import parse_repo
from dochealer.indexing.doc_parser import parse_docs
from dochealer.indexing.linker import build_graph
from dochealer.llm.client import LLMUnavailable
from dochealer.models import ChangedChunk


def graph_for(settings):
    return build_graph(parse_repo(settings), parse_docs(settings), settings)


def signature_change():
    """The fixture's true-stale case: get_user loses include_inactive."""
    return ChangedChunk(
        chunk_id="src/app.py::get_user", change_kind="modified",
        old_source=(
            "def get_user(user_id: int, include_inactive: bool = False) -> dict:\n"
            "    return {}"
        ),
        new_source="def get_user(user_id: int) -> dict:\n    return {}",
        old_signature="def get_user(user_id: int, include_inactive: bool=False) -> dict",
        new_signature="def get_user(user_id: int) -> dict",
    )


def test_find_suspects_maps_change_to_usage_section(settings):
    suspects = find_suspects(graph_for(settings), [signature_change()])
    ids = {section.id for section, _ in suspects}
    assert "docs/guide.md#sample-project-usage" in ids
    # unrelated sections not suspected
    assert "docs/guide.md#sample-project-unrelated-section" not in ids


def test_meaningless_change_never_reaches_llm(settings):
    """Fixture control case: whitespace edit is filtered before any LLM call."""
    change = ChangedChunk(
        chunk_id="src/app.py::get_user", change_kind="modified",
        old_source="def get_user(user_id: int) -> dict:\n    return {}",
        new_source="def get_user(user_id: int) -> dict:\n    return  {}",
        old_signature="def get_user(user_id: int) -> dict",
        new_signature="def get_user(user_id: int) -> dict",
    )
    meaningful = filter_meaningful([change])
    assert meaningful == []
    client = FakeLLMClient(responses=[])
    verdicts, skipped = verify_suspects(
        find_suspects(graph_for(settings), meaningful), client, settings
    )
    assert client.calls == []  # $0 spent (PRD flow C)
    assert verdicts == [] and skipped == []


def test_verify_returns_stale_verdict(settings):
    client = FakeLLMClient(responses=[
        ("get_user", {"stale": True,
                      "diagnosis": "Docs claim include_inactive exists; parameter was removed.",
                      "confidence": 0.95}),
        ("", {"stale": False, "diagnosis": "", "confidence": 0.9}),
    ])
    suspects = find_suspects(graph_for(settings), [signature_change()])
    verdicts, skipped = verify_suspects(suspects, client, settings)
    stale = [v for v in verdicts if v.stale]
    assert len(stale) == 1
    assert stale[0].section_id == "docs/guide.md#sample-project-usage"
    assert "include_inactive" in stale[0].diagnosis
    assert skipped == []


def test_verification_cap_enforced(settings):
    settings.max_verifications = 0
    client = FakeLLMClient(responses=[("", {"stale": False, "confidence": 0.9})])
    suspects = find_suspects(graph_for(settings), [signature_change()])
    verdicts, skipped = verify_suspects(suspects, client, settings)
    assert verdicts == []
    assert len(skipped) == len(suspects)
    assert client.calls == []


def test_llm_failure_degrades_to_skip(settings):
    client = FakeLLMClient(responses=[], fail=LLMUnavailable("boom"))
    suspects = find_suspects(graph_for(settings), [signature_change()])
    verdicts, skipped = verify_suspects(suspects, client, settings)
    assert verdicts == []
    assert len(skipped) == len(suspects)  # never raises (Rules.md §4)


def test_prompt_contains_old_new_and_docs(settings):
    client = FakeLLMClient(responses=[("", {"stale": False, "confidence": 0.8})])
    suspects = find_suspects(graph_for(settings), [signature_change()])
    verify_suspects(suspects, client, settings)
    prompt = client.calls[0]
    assert "OLD code" in prompt and "NEW code" in prompt
    assert "include_inactive" in prompt  # old code present
    assert "## Documentation section" in prompt
