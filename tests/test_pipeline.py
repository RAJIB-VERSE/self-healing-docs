"""Phase 4 tests: report rendering, correction splicing, e2e with fakes."""

from conftest import FIXTURE_REPO, FakeLLMClient
from dochealer.config import SUMMARY_MARKER
from dochealer.github.commenter import is_own_pr
from dochealer.github.pr_writer import apply_corrections_to_files, create_fix_pr, fix_pr_body
from dochealer.indexing.code_parser import parse_repo
from dochealer.indexing.doc_parser import parse_docs
from dochealer.indexing.linker import build_graph
from dochealer.main import run_pipeline
from dochealer.models import ChangedChunk, Correction, RunReport, StalenessVerdict
from dochealer.report import report_json, summary_comment

USAGE_ID = "docs/guide.md#sample-project-usage"
CORRECTED = (
    "## Usage\n\nCall `get_user()` with a user ID. Users can be removed with "
    "`delete_user()`."
)


class FakeGitHub:
    def __init__(self):
        self.branches, self.commits, self.prs, self.comments = [], [], [], []

    def create_fix_branch(self, branch):
        self.branches.append(branch)

    def commit_files(self, branch, files, message):
        self.commits.append((branch, files, message))

    def open_pr(self, branch, title, body, label):
        self.prs.append((branch, title, body, label))
        return "https://github.com/o/r/pull/99"

    def upsert_comment(self, pr_number, marker, body):
        self.comments.append((pr_number, marker, body))


def graph_for(settings):
    return build_graph(parse_repo(settings), parse_docs(settings), settings)


def correction(conf=0.92):
    return Correction(section_id=USAGE_ID, new_content=CORRECTED,
                      summary="Removed include_inactive parameter description",
                      validated=True, confidence=conf)


def test_loop_safety():
    assert is_own_pr("dochealer/fix-pr-12", [])
    assert is_own_pr("feature/x", ["dochealer"])
    assert not is_own_pr("feature/x", ["bug"])


def test_apply_corrections_splices_section(settings):
    graph = graph_for(settings)
    files = apply_corrections_to_files([correction()], graph, FIXTURE_REPO)
    assert set(files) == {"docs/guide.md"}
    new_text = files["docs/guide.md"]
    assert "include_inactive" not in new_text.split("## Configuration")[0]
    # untouched sections preserved verbatim
    assert "### Retries" in new_text
    assert "defaults to **5 seconds**" in new_text
    assert "## Unrelated section" in new_text
    # original file on disk unchanged
    assert "include_inactive" in (FIXTURE_REPO / "docs/guide.md").read_text(encoding="utf-8")


def test_fix_pr_body_contents(settings):
    body = fix_pr_body([correction()], graph_for(settings), source_pr=7)
    assert "Doc fixes for #7" in body
    assert "Sample project › Usage" in body
    assert "confidence 0.92" in body
    assert "Review checklist" in body


def test_create_fix_pr_flow(settings):
    settings.pr_number = 7
    backend = FakeGitHub()
    url = create_fix_pr([correction()], graph_for(settings), settings, backend)
    assert url == "https://github.com/o/r/pull/99"
    assert backend.branches == ["dochealer/fix-pr-7"]
    branch, files, message = backend.commits[0]
    assert "docs/guide.md" in files
    assert "#7" in message
    _, title, _, label = backend.prs[0]
    assert label == "dochealer"


def test_summary_comment_all_outcomes(settings):
    graph = graph_for(settings)
    report = RunReport(
        analyzed_changes=4,
        verified_ok=["docs/guide.md#sample-project-configuration-retries"],
        fixed=[correction()],
        flagged=[StalenessVerdict(section_id="docs/guide.md#sample-project-configuration-timeouts",
                                  stale=True, diagnosis="default changed 30->60", confidence=0.6)],
        fix_pr_url="https://github.com/o/r/pull/99",
    )
    body = summary_comment(report, graph)
    assert body.startswith(SUMMARY_MARKER)
    assert "1 section verified accurate" in body
    assert "🩹 1 auto-fixed → https://github.com/o/r/pull/99" in body
    assert "⚠️ 1 flagged for review" in body
    assert "docs/guide.md#L" in body  # section links
    assert "4 code changes analyzed" in body


def test_summary_comment_no_impact(settings):
    body = summary_comment(RunReport(analyzed_changes=0), graph_for(settings))
    assert "No doc-impacting changes detected" in body


def test_report_json_counts():
    payload = report_json(RunReport(fixed=[correction()], verified_ok=["a"], skipped=["b"]))
    assert payload["stale_count"] == 1
    assert payload["fixed_count"] == 1
    assert payload["flagged_count"] == 0
    assert payload["llm_calls"] == 0
    assert payload["skipped"] == ["b"]


def test_e2e_pipeline_to_github(settings):
    """Full flow: change → verify → correct → validate → fix PR + comment."""
    settings.pr_number = 7
    graph = graph_for(settings)
    change = ChangedChunk(
        chunk_id="src/app.py::get_user", change_kind="modified",
        old_source="def get_user(user_id, include_inactive=False): ...",
        new_source="def get_user(user_id): ...",
        old_signature="def get_user(user_id, include_inactive=False)",
        new_signature="def get_user(user_id)",
    )
    client = FakeLLMClient(responses=[
        ("Run the three checks", {"passes": True, "problems": [], "confidence": 0.94}),
        ("Staleness diagnosis", {"new_content": CORRECTED,
                                 "summary": "Removed include_inactive",
                                 "confidence": 0.92}),
        ("Is the documentation section still accurate",
         {"stale": True, "diagnosis": "include_inactive removed", "confidence": 0.95}),
    ])
    report = run_pipeline(settings, graph, [change], client)
    assert len(report.fixed) == 1

    backend = FakeGitHub()
    report.fix_pr_url = create_fix_pr(report.fixed, graph, settings, backend)
    backend.upsert_comment(7, SUMMARY_MARKER, summary_comment(report, graph))

    assert backend.prs and backend.comments
    _, _, comment_body = backend.comments[0]
    assert "🩹 1 auto-fixed → https://github.com/o/r/pull/99" in comment_body
