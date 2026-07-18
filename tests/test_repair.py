"""Phase 3 tests: correction generation, validation gate, confidence routing."""
from conftest import FakeLLMClient
from dochealer.indexing.code_parser import parse_repo
from dochealer.indexing.doc_parser import parse_docs
from dochealer.indexing.linker import build_graph
from dochealer.llm.client import LLMUnavailable
from dochealer.main import run_pipeline
from dochealer.models import ChangedChunk, StalenessVerdict
from dochealer.repair.corrector import generate_correction
from dochealer.repair.validator import validate_correction

CORRECTED = (
    "## Usage\n\nCall `get_user()` with a user ID. Users can be removed with "
    "`delete_user()`.\n"
)

STALE_VERDICT = {
    "stale": True,
    "diagnosis": "Docs describe include_inactive; the parameter was removed.",
    "confidence": 0.95,
}
OK_VERDICT = {"stale": False, "diagnosis": "", "confidence": 0.9}
GOOD_CORRECTION = {"new_content": CORRECTED,
                   "summary": "Removed include_inactive parameter description",
                   "confidence": 0.92}
PASS_VALIDATION = {"passes": True, "problems": [], "confidence": 0.94}
FAIL_VALIDATION = {"passes": False, "problems": ["dropped delete_user sentence"],
                   "confidence": 0.9}


def graph_for(settings):
    return build_graph(parse_repo(settings), parse_docs(settings), settings)


def signature_change():
    return ChangedChunk(
        chunk_id="src/app.py::get_user", change_kind="modified",
        old_source="def get_user(user_id, include_inactive=False): ...",
        new_source="def get_user(user_id): ...",
        old_signature="def get_user(user_id, include_inactive=False)",
        new_signature="def get_user(user_id)",
    )


def usage_section(settings):
    return graph_for(settings).section_by_id("docs/guide.md#sample-project-usage")


def verdict():
    return StalenessVerdict(section_id="docs/guide.md#sample-project-usage",
                            **STALE_VERDICT)


def test_correction_generated(settings):
    client = FakeLLMClient(responses=[("", GOOD_CORRECTION)])
    correction = generate_correction(
        usage_section(settings), verdict(), [signature_change()], client, settings
    )
    assert correction is not None
    assert correction.new_content == CORRECTED
    assert correction.todo_markers == []
    prompt = client.calls[0]
    assert "Staleness diagnosis" in prompt and "NEW code" in prompt


def test_correction_captures_todo_markers(settings):
    payload = dict(GOOD_CORRECTION)
    payload["new_content"] = CORRECTED + "\n<!-- TODO(dochealer): document new auth flow -->\n"
    client = FakeLLMClient(responses=[("", payload)])
    correction = generate_correction(
        usage_section(settings), verdict(), [signature_change()], client, settings
    )
    assert len(correction.todo_markers) == 1


def test_correction_none_on_llm_failure(settings):
    client = FakeLLMClient(responses=[], fail=LLMUnavailable("down"))
    assert generate_correction(
        usage_section(settings), verdict(), [signature_change()], client, settings
    ) is None


def test_prompt_echo_stripped(settings):
    """Smaller models echo prompt scaffolding above the section; it must be cut."""
    echoed = dict(GOOD_CORRECTION)
    echoed["new_content"] = (
        "## Current documentation section (Sample project › Usage)\n\n" + CORRECTED
    )
    client = FakeLLMClient(responses=[("", echoed)])
    correction = generate_correction(
        usage_section(settings), verdict(), [signature_change()], client, settings
    )
    assert correction.new_content == CORRECTED.rstrip("\n")
    assert "Current documentation section" not in correction.new_content


def test_validation_pass_sets_min_confidence(settings):
    gen = FakeLLMClient(responses=[("", GOOD_CORRECTION)])
    correction = generate_correction(
        usage_section(settings), verdict(), [signature_change()], gen, settings
    )
    val = FakeLLMClient(responses=[("", PASS_VALIDATION)])
    validated = validate_correction(
        usage_section(settings), correction, [signature_change()], val, settings
    )
    assert validated.validated is True
    assert validated.confidence == min(0.92, 0.94)


def test_validation_failure_marks_unvalidated(settings):
    gen = FakeLLMClient(responses=[("", GOOD_CORRECTION)])
    correction = generate_correction(
        usage_section(settings), verdict(), [signature_change()], gen, settings
    )
    val = FakeLLMClient(responses=[("", FAIL_VALIDATION)])
    validated = validate_correction(
        usage_section(settings), correction, [signature_change()], val, settings
    )
    assert validated.validated is False


# --- pipeline routing (Phase 3.3 gate) ---


def pipeline_client(validation=PASS_VALIDATION, correction=GOOD_CORRECTION):
    """Canned responses for verify → correct → validate, keyed by prompt markers."""
    return FakeLLMClient(responses=[
        ("Run the three checks", validation),          # validator prompt
        ("Staleness diagnosis", correction),           # corrector prompt
        ("Is the documentation section still accurate", STALE_VERDICT),  # verifier
    ])


def test_pipeline_high_confidence_routes_to_fixed(settings):
    report = run_pipeline(settings, graph_for(settings), [signature_change()],
                          pipeline_client())
    assert len(report.fixed) == 1
    assert report.fixed[0].section_id == "docs/guide.md#sample-project-usage"
    assert report.flagged == []


def test_pipeline_low_confidence_routes_to_flagged(settings):
    low = dict(GOOD_CORRECTION, confidence=0.4)
    report = run_pipeline(settings, graph_for(settings), [signature_change()],
                          pipeline_client(correction=low))
    assert report.fixed == []
    assert len(report.flagged) == 1


def test_pipeline_failed_validation_routes_to_flagged(settings):
    report = run_pipeline(settings, graph_for(settings), [signature_change()],
                          pipeline_client(validation=FAIL_VALIDATION))
    assert report.fixed == []
    assert len(report.flagged) == 1


def test_pipeline_flag_only_mode_skips_correction(settings):
    settings.mode = "flag-only"
    client = FakeLLMClient(responses=[
        ("Is the documentation section still accurate", STALE_VERDICT),
    ])
    report = run_pipeline(settings, graph_for(settings), [signature_change()], client)
    assert report.fixed == []
    assert len(report.flagged) == 1
    # only the verification call happened
    assert len(client.calls) == 1


def test_pipeline_meaningless_change_short_circuits(settings):
    change = ChangedChunk(
        chunk_id="src/app.py::get_user", change_kind="modified",
        old_source="def get_user(user_id):\n    return {}",
        new_source="def get_user(user_id):\n    return  {}",
        old_signature="def get_user(user_id)", new_signature="def get_user(user_id)",
    )
    client = FakeLLMClient(responses=[])
    report = run_pipeline(settings, graph_for(settings), [change], client)
    assert client.calls == []
    assert report.fixed == report.flagged == []
    assert report.analyzed_changes == 1
