"""Parse Python source files into CodeChunks using the stdlib ast module.

Extracts: module-level functions, classes, methods, argparse/click CLI commands
(detected by decorator/call heuristics), and module-level config constants.
Unparseable files are skipped with a warning (Rules.md §4).
"""
from __future__ import annotations

import ast
import logging
import re
from pathlib import Path

from dochealer.config import Settings
from dochealer.models import ChunkKind, CodeChunk

log = logging.getLogger(__name__)

_CLI_DECORATORS = {"command", "group", "app.command", "cli.command"}
_CONFIG_BASE_NAMES = {"BaseSettings", "BaseModel"}  # pydantic config-ish classes
_CONST_NAME_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*$")  # UPPER_SNAKE


def parse_repo(settings: Settings) -> list[CodeChunk]:
    """Walk the repo and parse every matching source file."""
    chunks: list[CodeChunk] = []
    root = settings.repo_root
    for pattern in settings.code_globs:
        for file in sorted(root.glob(pattern)):
            rel_parts = file.relative_to(root).parts
            if any(part in settings.ignore_dirs for part in rel_parts):
                continue
            chunks.extend(parse_file(file, root))
    return chunks


def parse_file(file: Path, root: Path) -> list[CodeChunk]:
    rel = file.relative_to(root).as_posix()
    try:
        source = file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as exc:
        log.warning("[index] skipping unreadable file %s: %s", rel, exc)
        return []
    return parse_source(source, rel)


def parse_source(source: str, rel_path: str) -> list[CodeChunk]:
    """Parse already-loaded source text. Separated for diff-time reuse."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        log.warning("[index] skipping unparseable source %s: %s", rel_path, exc)
        return []
    lines = source.splitlines()
    chunks: list[CodeChunk] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chunks.append(_function_chunk(node, rel_path, lines, parent=None))
        elif isinstance(node, ast.ClassDef):
            chunks.append(_class_chunk(node, rel_path, lines))
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    chunks.append(_function_chunk(item, rel_path, lines, parent=node.name))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            const = _constant_chunk(node, rel_path, lines)
            if const is not None:
                chunks.append(const)
    return chunks


def _segment(lines: list[str], node: ast.stmt) -> str:
    return "\n".join(lines[node.lineno - 1 : node.end_lineno])


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args = ast.unparse(node.args)
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    return f"{prefix} {node.name}({args}){ret}"


def _function_kind(node: ast.FunctionDef | ast.AsyncFunctionDef, parent: str | None) -> ChunkKind:
    for dec in node.decorator_list:
        name = ast.unparse(dec).split("(")[0]
        if name in _CLI_DECORATORS or name.endswith(".command"):
            return "cli"
    return "method" if parent else "function"


def _function_chunk(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    rel_path: str,
    lines: list[str],
    parent: str | None,
) -> CodeChunk:
    qualname = f"{parent}.{node.name}" if parent else node.name
    return CodeChunk(
        path=rel_path,
        kind=_function_kind(node, parent),
        name=node.name,
        qualname=qualname,
        signature=_signature(node),
        docstring=ast.get_docstring(node) or "",
        source=_segment(lines, node),
        lineno=node.lineno,
        end_lineno=node.end_lineno or node.lineno,
    )


def _class_chunk(node: ast.ClassDef, rel_path: str, lines: list[str]) -> CodeChunk:
    bases = [ast.unparse(b) for b in node.bases]
    is_config = any(b.split(".")[-1] in _CONFIG_BASE_NAMES for b in bases)
    kind: ChunkKind = "config" if is_config else "class"
    base_str = f"({', '.join(bases)})" if bases else ""
    return CodeChunk(
        path=rel_path,
        kind=kind,
        name=node.name,
        qualname=node.name,
        signature=f"class {node.name}{base_str}",
        docstring=ast.get_docstring(node) or "",
        source=_segment(lines, node),
        lineno=node.lineno,
        end_lineno=node.end_lineno or node.lineno,
    )


def _constant_chunk(
    node: ast.Assign | ast.AnnAssign, rel_path: str, lines: list[str]
) -> CodeChunk | None:
    """Module-level UPPER_SNAKE constants (e.g. DEFAULT_TIMEOUT = 30) as config chunks.

    Docs frequently state default values; without these chunks a changed constant
    would never be linked to the section describing it (Memory.md decision #3).
    """
    if isinstance(node, ast.Assign):
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            return None
        name = node.targets[0].id
    else:  # AnnAssign
        if not isinstance(node.target, ast.Name) or node.value is None:
            return None
        name = node.target.id
    if not _CONST_NAME_RE.match(name):
        return None
    return CodeChunk(
        path=rel_path,
        kind="config",
        name=name,
        qualname=name,
        signature=_segment(lines, node).splitlines()[0],
        source=_segment(lines, node),
        lineno=node.lineno,
        end_lineno=node.end_lineno or node.lineno,
    )
