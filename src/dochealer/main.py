"""Entrypoint: CLI for local use + Action orchestration.

Pipeline stages per Architecture.md §6. GitHub side effects (REPORT stage)
attach in Phase 4; run_pipeline itself is pure given an injected LLM client.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from dochealer.config import Settings
from dochealer.detection.change_filter import filter_meaningful
from dochealer.detection.diff_parser import diff_to_changed_chunks
from dochealer.detection.staleness import find_suspects, verify_suspects
from dochealer.indexing.code_parser import parse_repo
from dochealer.indexing.doc_parser import parse_docs
from dochealer.indexing.linker import build_graph, load_graph, save_graph
from dochealer.llm.client import LLMClient
from dochealer.models import ChangedChunk, LinkGraph, RunReport
from dochealer.repair.corrector import generate_correction
from dochealer.repair.validator import validate_correction

log = logging.getLogger("dochealer")


def build_index(settings: Settings) -> LinkGraph:
    """INDEX stage: parse code + docs, link, persist."""
    chunks = parse_repo(settings)
    sections = parse_docs(settings)
    embedder = None
    if settings.llm_api_key and settings.llm_provider in ("openai", "github"):
        from dochealer.indexing.embedder import OpenAIEmbedder
        from dochealer.llm.client import GITHUB_MODELS_BASE_URL

        base_url = GITHUB_MODELS_BASE_URL if settings.llm_provider == "github" else ""
        model = settings.embedding_model
        if settings.llm_provider == "github" and "/" not in model:
            model = f"openai/{model}"  # GitHub Models namespaces model IDs
        embedder = OpenAIEmbedder(settings.llm_api_key, model, base_url=base_url)
    graph = build_graph(chunks, sections, settings, embedder=embedder)
    save_graph(graph, settings.index_path)
    log.info("[index] wrote %s", settings.index_path)
    return graph


def load_or_build_index(settings: Settings) -> LinkGraph:
    graph = load_graph(settings.index_path)
    if graph is None:
        graph = build_index(settings)
    return graph


def run_pipeline(
    settings: Settings,
    graph: LinkGraph,
    changes: list[ChangedChunk],
    client: LLMClient,
) -> RunReport:
    """DETECT + REPAIR stages with confidence routing (Phases.md Phase 3.3)."""
    report = RunReport(analyzed_changes=len(changes))

    # DETECT: filter → suspects → verify
    meaningful = filter_meaningful(changes)
    if not meaningful:
        log.info("[detect] no doc-impacting changes")
        return report
    suspects = find_suspects(graph, meaningful)
    log.info("[detect] %d meaningful changes → %d suspect sections",
             len(meaningful), len(suspects))
    verdicts, skipped = verify_suspects(suspects, client, settings)
    report.skipped.extend(skipped)
    changes_by_section = {section.id: chs for section, chs in suspects}

    corrections_budget = settings.max_corrections
    for verdict in verdicts:
        if not verdict.stale:
            report.verified_ok.append(verdict.section_id)
            continue

        # REPAIR path
        section = graph.section_by_id(verdict.section_id)
        if section is None:  # index out of date; treat as flag
            report.flagged.append(verdict)
            continue
        if settings.mode == "flag-only" or corrections_budget <= 0:
            report.flagged.append(verdict)
            continue

        correction = generate_correction(
            section, verdict, changes_by_section[verdict.section_id], client, settings
        )
        if correction is None:
            report.flagged.append(verdict)
            continue
        corrections_budget -= 1
        correction = validate_correction(
            section, correction, changes_by_section[verdict.section_id], client, settings,
            diagnosis=verdict.diagnosis,
        )

        confidence = min(verdict.confidence, correction.confidence)
        auto_fixable = (
            correction.validated
            and confidence >= settings.confidence_threshold
            and not correction.todo_markers
        )
        if auto_fixable:
            report.fixed.append(correction)
            log.info("[repair] auto-fix %s (conf %.2f)", section.id, confidence)
        else:
            report.flagged.append(verdict)
            log.info("[repair] flagged %s (validated=%s conf %.2f todos=%d)",
                     section.id, correction.validated, confidence,
                     len(correction.todo_markers))
    if corrections_budget <= 0:
        report.notes.append("correction cap reached; remaining stale sections flagged")
    report.llm_calls = getattr(client, "calls_made", 0)
    return report


def detect_changes(settings: Settings, base_ref: str, head_ref: str = "HEAD") -> list[ChangedChunk]:
    return diff_to_changed_chunks(settings.repo_root, base_ref, head_ref)


def run_action(settings: Settings, base_ref: str, head_branch: str, labels: list[str]) -> int:
    """Full Action run: index → detect → repair → report. Never fails the host PR."""
    import json
    import os

    from dochealer.github.commenter import LiveGitHub, is_own_pr
    from dochealer.github.pr_writer import create_fix_pr
    from dochealer.llm.client import make_client
    from dochealer.report import report_json, summary_comment

    if is_own_pr(head_branch, labels):
        log.info("[report] skipping dochealer's own PR (loop safety)")
        return 0

    graph = load_or_build_index(settings)
    try:
        changes = detect_changes(settings, base_ref)
    except Exception as exc:  # noqa: BLE001 — infra failure must not fail the PR
        log.warning("[detect] diff failed: %s", exc)
        changes = []

    client = make_client(settings.llm_provider, settings.llm_api_key, settings.llm_model)
    report = run_pipeline(settings, graph, changes, client)

    backend = LiveGitHub(settings)
    if report.fixed and settings.mode == "fix":
        try:
            report.fix_pr_url = create_fix_pr(report.fixed, graph, settings, backend)
        except Exception as exc:  # noqa: BLE001
            log.warning("[report] fix PR failed: %s — downgrading fixes to flags", exc)
            report.notes.append(f"fix PR creation failed: {exc}")
    from dochealer.config import SUMMARY_MARKER

    try:
        backend.upsert_comment(settings.pr_number, SUMMARY_MARKER,
                               summary_comment(report, graph))
    except Exception as exc:  # noqa: BLE001
        log.warning("[report] summary comment failed: %s", exc)

    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        payload = report_json(report)
        with open(output_path, "a", encoding="utf-8") as fh:
            for key in ("stale_count", "fixed_count", "flagged_count"):
                fh.write(f"{key.replace('_', '-')}={payload[key]}\n")
            fh.write(f"fix-pr-url={report.fix_pr_url}\n")
            fh.write(f"report-json={json.dumps(payload)}\n")
    return 0


def run_check(settings: Settings, base_ref: str, apply: bool) -> int:
    """Local pre-push check: run the pipeline against uncommitted/branch changes.

    Prints the report to the terminal; --apply writes auto-fixes into the
    working tree (no git side effects — you review and commit yourself).
    """
    from dochealer.github.pr_writer import apply_corrections_to_files
    from dochealer.llm.client import make_client
    from dochealer.report import report_json

    if not settings.llm_api_key:
        log.error("[check] no API key: set DOCHEALER_LLM_API_KEY "
                  "(a GitHub token works with DOCHEALER_LLM_PROVIDER=github)")
        return 2

    graph = load_or_build_index(settings)
    changes = detect_changes(settings, base_ref)
    client = make_client(settings.llm_provider, settings.llm_api_key, settings.llm_model)
    report = run_pipeline(settings, graph, changes, client)

    print()  # summary block per Design.md §3
    print(f"[report] {len(report.verified_ok)} verified accurate · "
          f"{len(report.fixed)} auto-fixable · {len(report.flagged)} need review · "
          f"{len(report.skipped)} skipped · {report.llm_calls} LLM calls")
    for verdict in report.flagged:
        print(f"[report] REVIEW {verdict.section_id}: {verdict.diagnosis}")
    for correction in report.fixed:
        print(f"[report] FIX {correction.section_id}: {correction.summary}")

    if apply and report.fixed:
        files = apply_corrections_to_files(report.fixed, graph, settings.repo_root)
        for rel_path, content in files.items():
            (settings.repo_root / rel_path).write_text(content, encoding="utf-8")
            print(f"[report] wrote {rel_path}")
    elif report.fixed:
        print("[report] run again with --apply to write these fixes to disk")

    import json

    print(json.dumps(report_json(report), indent=2))
    # exit 1 when staleness found → usable in pre-push hooks / CI gates
    return 1 if (report.fixed or report.flagged) else 0


def cli(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(prog="dochealer")
    sub = parser.add_subparsers(dest="command", required=True)

    index_cmd = sub.add_parser("index", help="build the code-to-docs index")
    index_cmd.add_argument("--repo", default=".", help="repo root (default: cwd)")
    index_cmd.add_argument("--docs-path", default="docs")

    run_cmd = sub.add_parser("run", help="full pipeline (inside the GitHub Action)")
    run_cmd.add_argument("--base-ref", required=True)
    run_cmd.add_argument("--head-branch", default="")
    run_cmd.add_argument("--labels", default="", help="comma-separated PR labels")

    check_cmd = sub.add_parser("check", help="local pre-push doc check (no GitHub needed)")
    check_cmd.add_argument("--repo", default=".", help="repo root (default: cwd)")
    check_cmd.add_argument("--base-ref", default="main",
                           help="ref to diff against (default: main)")
    check_cmd.add_argument("--docs-path", default="docs")
    check_cmd.add_argument("--apply", action="store_true",
                           help="write auto-fixes into the working tree")

    args = parser.parse_args(argv)
    if args.command == "index":
        settings = Settings.from_env(repo_root=Path(args.repo).resolve())
        settings.docs_path = args.docs_path
        build_index(settings)
    elif args.command == "run":
        settings = Settings.from_env()
        labels = [x.strip() for x in args.labels.split(",") if x.strip()]
        return run_action(settings, args.base_ref, args.head_branch, labels)
    elif args.command == "check":
        settings = Settings.from_env(repo_root=Path(args.repo).resolve())
        settings.docs_path = args.docs_path
        return run_check(settings, args.base_ref, args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(cli())
