"""Turn a git diff into ChangedChunks.

Strategy (Architecture.md Phase 2.1): parse `git diff base...head` unified output
for changed files + line ranges on the NEW side, then re-parse old/new file
versions into chunks and classify each as added / removed / modified by
intersecting changed ranges with chunk line spans.
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from dochealer.indexing.code_parser import parse_source
from dochealer.models import ChangedChunk, CodeChunk

log = logging.getLogger(__name__)

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120, check=True
    )
    return result.stdout


def changed_python_files(diff_text: str) -> dict[str, list[tuple[int, int]]]:
    """Map new-side file path -> list of changed (start, end) line ranges.

    Deleted files appear with an empty range list keyed by their OLD path.
    """
    files: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path == "/dev/null":
                current = None  # deletion; keyed below via "--- a/..."
                continue
            current = path.removeprefix("b/")
            if current.endswith(".py"):
                files.setdefault(current, [])
            else:
                current = None
        elif line.startswith("--- ") and current is None:
            old = line[4:].strip().removeprefix("a/")
            if old != "/dev/null" and old.endswith(".py"):
                files.setdefault(old, [])
        elif current and (m := _HUNK_RE.match(line)):
            start = int(m.group(3))
            count = int(m.group(4) or "1")
            # count==0 means pure deletion at this position; still mark the line
            files[current].append((start, max(start, start + count - 1)))
    return files


def _overlaps(chunk: CodeChunk, ranges: list[tuple[int, int]]) -> bool:
    return any(not (end < chunk.lineno or start > chunk.end_lineno) for start, end in ranges)


def diff_to_changed_chunks(
    repo_root: Path, base_ref: str, head_ref: str = "HEAD"
) -> list[ChangedChunk]:
    """Compute ChangedChunks between two refs using git + the AST parser."""
    diff_text = run_git(["diff", "--unified=0", f"{base_ref}...{head_ref}", "--", "*.py"],
                        cwd=repo_root)
    changed = changed_python_files(diff_text)
    out: list[ChangedChunk] = []
    for path, ranges in changed.items():
        old_src = _show(repo_root, base_ref, path)
        new_src = _show(repo_root, head_ref, path)
        out.extend(compare_versions(path, old_src, new_src, ranges))
    return out


def _show(repo_root: Path, ref: str, path: str) -> str:
    try:
        return run_git(["show", f"{ref}:{path}"], cwd=repo_root)
    except subprocess.CalledProcessError:
        return ""  # file absent at this ref (added or deleted)


def compare_versions(
    path: str, old_source: str, new_source: str, changed_ranges: list[tuple[int, int]]
) -> list[ChangedChunk]:
    """Classify chunk-level changes between two versions of one file.

    changed_ranges (new-side) limits "modified" detection to chunks the diff
    actually touched, so unrelated chunks in a file don't become suspects.
    """
    old_chunks = {c.qualname: c for c in parse_source(old_source, path)} if old_source else {}
    new_chunks = {c.qualname: c for c in parse_source(new_source, path)} if new_source else {}

    out: list[ChangedChunk] = []
    for qualname, new_chunk in new_chunks.items():
        old_chunk = old_chunks.get(qualname)
        if old_chunk is None:
            out.append(ChangedChunk(
                chunk_id=new_chunk.id, change_kind="added",
                new_source=new_chunk.source, new_signature=new_chunk.signature,
            ))
        elif old_chunk.source != new_chunk.source and (
            not changed_ranges or _overlaps(new_chunk, changed_ranges)
        ):
            out.append(ChangedChunk(
                chunk_id=new_chunk.id, change_kind="modified",
                old_source=old_chunk.source, new_source=new_chunk.source,
                old_signature=old_chunk.signature, new_signature=new_chunk.signature,
            ))
    for qualname, old_chunk in old_chunks.items():
        if qualname not in new_chunks:
            out.append(ChangedChunk(
                chunk_id=old_chunk.id, change_kind="removed",
                old_source=old_chunk.source, old_signature=old_chunk.signature,
            ))
    return out
