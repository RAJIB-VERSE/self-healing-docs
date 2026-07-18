"""Render a RunReport as the PR summary comment and machine-readable JSON.

Comment design follows Design.md §2: verdict first, status glyphs, collapsible
detail, hidden upsert marker.
"""
from __future__ import annotations

from dochealer.config import SUMMARY_MARKER
from dochealer.models import LinkGraph, RunReport, StalenessVerdict


def _section_link(graph: LinkGraph, section_id: str) -> str:
    section = graph.section_by_id(section_id)
    if section is None:
        return f"`{section_id}`"
    return f"[{section.title}]({section.path}#L{section.lineno})"


def _flag_row(graph: LinkGraph, verdict: StalenessVerdict) -> str:
    diagnosis = verdict.diagnosis.replace("|", "\\|").replace("\n", " ")
    return f"| {_section_link(graph, verdict.section_id)} | {diagnosis} |"


def summary_comment(report: RunReport, graph: LinkGraph) -> str:
    ok, fixed, flagged = len(report.verified_ok), len(report.fixed), len(report.flagged)
    parts = [SUMMARY_MARKER, "### 🩺 Doc Check Results"]

    if report.analyzed_changes == 0 or (ok + fixed + flagged == 0 and not report.skipped):
        parts.append("No doc-impacting changes detected. ✅")
    else:
        bits = []
        if ok:
            bits.append(f"✅ {ok} section{'s' if ok != 1 else ''} verified accurate")
        if fixed:
            target = f" → {report.fix_pr_url}" if report.fix_pr_url else ""
            bits.append(f"🩹 {fixed} auto-fixed{target}")
        if flagged:
            bits.append(f"⚠️ {flagged} flagged for review")
        if report.skipped:
            bits.append(f"⏭️ {len(report.skipped)} skipped")
        parts.append(" · ".join(bits) if bits else "No stale documentation found. ✅")

    if report.fixed:
        rows = "\n".join(
            f"| {_section_link(graph, c.section_id)} | {c.summary} |" for c in report.fixed
        )
        parts.append(
            "\n<details><summary>🩹 Auto-fixed sections</summary>\n\n"
            "| Section | Fix |\n|---|---|\n" + rows + "\n</details>"
        )
    if report.flagged:
        rows = "\n".join(_flag_row(graph, v) for v in report.flagged)
        parts.append(
            "\n<details><summary>⚠️ Sections needing review</summary>\n\n"
            "| Section | Why it's suspect |\n|---|---|\n" + rows + "\n</details>"
        )
    for note in report.notes:
        parts.append(f"\n> ⚠️ {note}")

    parts.append(
        f"\n<sub>dochealer · {report.analyzed_changes} code "
        f"change{'s' if report.analyzed_changes != 1 else ''} analyzed · "
        f"{report.llm_calls} LLM call{'s' if report.llm_calls != 1 else ''}</sub>"
    )
    return "\n".join(parts)


def report_json(report: RunReport) -> dict:
    return {
        "stale_count": len(report.fixed) + len(report.flagged),
        "fixed_count": len(report.fixed),
        "flagged_count": len(report.flagged),
        "verified_ok_count": len(report.verified_ok),
        "llm_calls": report.llm_calls,
        "skipped": report.skipped,
        "fix_pr_url": report.fix_pr_url,
        "notes": report.notes,
    }
