"""Filter ChangedChunks down to meaningful, doc-relevant changes.

Dropped (Phases.md Phase 2.2): test files, comment/whitespace-only edits,
docstring-only edits, private chunks nobody documents. Kept: signature changes,
added/removed public chunks, body changes.
"""
from __future__ import annotations

import ast
import io
import logging
import tokenize

from dochealer.models import ChangedChunk

log = logging.getLogger(__name__)

_TEST_MARKERS = ("test_", "_test.py", "conftest.py")


def is_test_file(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (
        name.startswith(_TEST_MARKERS[0])
        or name.endswith(_TEST_MARKERS[1])
        or name == _TEST_MARKERS[2]
        or "/tests/" in f"/{path}"
    )


def _normalize(source: str) -> str:
    """Strip comments, whitespace and docstrings so behavior-identical code compares equal."""
    # remove comments via tokenize; fall back to raw text on failure
    try:
        tokens = [
            t for t in tokenize.generate_tokens(io.StringIO(source).readline)
            if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                              tokenize.DEDENT)
        ]
        stripped = " ".join(t.string.strip() for t in tokens if t.string.strip())
    except (tokenize.TokenizeError, IndentationError):
        stripped = source
    # remove docstrings via AST round-trip when parseable
    try:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                body = node.body
                if (body and isinstance(body[0], ast.Expr)
                        and isinstance(body[0].value, ast.Constant)
                        and isinstance(body[0].value.value, str)):
                    node.body = body[1:] or [ast.Pass()]
        return ast.unparse(tree)
    except SyntaxError:
        return stripped


def is_meaningful(change: ChangedChunk) -> bool:
    """Would this change plausibly affect documentation?"""
    path = change.chunk_id.split("::")[0]
    name = change.chunk_id.split("::")[-1].split(".")[-1]

    if is_test_file(path):
        return False
    if name.startswith("_"):  # private; docs don't cover these
        return False
    if change.change_kind in ("added", "removed"):
        return True
    # modified: signature change is always meaningful
    if change.old_signature != change.new_signature:
        return True
    # body change that survives comment/docstring/whitespace normalization
    return _normalize(change.old_source) != _normalize(change.new_source)


def filter_meaningful(changes: list[ChangedChunk]) -> list[ChangedChunk]:
    kept = [c for c in changes if is_meaningful(c)]
    for c in changes:
        if c not in kept:
            log.info("[detect] filtered non-meaningful change: %s", c.chunk_id)
    return kept
