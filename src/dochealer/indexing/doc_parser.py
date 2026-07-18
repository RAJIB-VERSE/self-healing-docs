"""Parse markdown documentation into DocSections split by heading.

Each section carries its heading path (e.g. Configuration > Environment Variables)
and the code references it mentions: backticked identifiers, --cli-flags,
UPPER_SNAKE config keys, and dotted/called names in prose.
"""
from __future__ import annotations

import re
from pathlib import Path

from dochealer.config import Settings
from dochealer.models import DocSection

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^(```|~~~)")

# code-reference extractors, applied to section content
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][\w.]*(\(\))?$")
_CLI_FLAG_RE = re.compile(r"(?<!\w)(--[a-z][\w-]+)")
_UPPER_SNAKE_RE = re.compile(r"\b([A-Z][A-Z0-9]+(?:_[A-Z0-9]+)+)\b")
_CALLED_NAME_RE = re.compile(r"\b([a-z_][\w]*)\(\)")


def parse_docs(settings: Settings) -> list[DocSection]:
    """Parse all markdown files under docs_path (+ README if configured)."""
    root = settings.repo_root
    files: list[Path] = []
    docs_dir = root / settings.docs_path
    if docs_dir.is_dir():
        files.extend(sorted(docs_dir.rglob("*.md")))
    if settings.include_readme:
        for name in ("README.md", "readme.md"):
            candidate = root / name
            if candidate.is_file():
                files.append(candidate)
                break
    sections: list[DocSection] = []
    for file in files:
        rel = file.relative_to(root).as_posix()
        sections.extend(parse_markdown(file.read_text(encoding="utf-8"), rel))
    return sections


def parse_markdown(text: str, rel_path: str) -> list[DocSection]:
    """Split one markdown document into heading-delimited sections.

    A section spans from its heading to the next heading of any level.
    Content before the first heading becomes a level-0 "(intro)" section.
    Headings inside fenced code blocks are ignored.
    """
    lines = text.splitlines()
    # (level, title, start_line) for every real heading
    headings: list[tuple[int, str, int]] = []
    in_fence = False
    for i, line in enumerate(lines, start=1):
        if _FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if m:
            headings.append((len(m.group(1)), m.group(2), i))

    sections: list[DocSection] = []

    def add(level: int, title_stack: tuple[str, ...], start: int, end: int) -> None:
        content = "\n".join(lines[start - 1 : end])
        if not content.strip():
            return
        sections.append(
            DocSection(
                path=rel_path,
                heading_path=title_stack,
                level=level,
                content=content,
                code_refs=extract_code_refs(content),
                lineno=start,
                end_lineno=end,
            )
        )

    if headings and headings[0][2] > 1:
        add(0, ("(intro)",), 1, headings[0][2] - 1)
    elif not headings:
        add(0, ("(intro)",), 1, len(lines))
        return sections

    stack: list[tuple[int, str]] = []  # (level, title)
    for idx, (level, title, start) in enumerate(headings):
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        end = headings[idx + 1][2] - 1 if idx + 1 < len(headings) else len(lines)
        add(level, tuple(t for _, t in stack), start, end)
    return sections


def extract_code_refs(content: str) -> list[str]:
    """Pull likely code identifiers out of a section's markdown."""
    refs: set[str] = set()
    # strip fenced blocks first so we don't harvest whole code samples,
    # but keep their content aside: identifiers *defined* there still count via prose
    prose = re.sub(r"(```|~~~).*?\1", " ", content, flags=re.DOTALL)

    for m in _BACKTICK_RE.finditer(prose):
        token = m.group(1).strip()
        bare = token.removesuffix("()")
        if _IDENTIFIER_RE.match(token) and not token.isdigit():
            refs.add(bare)
        for flag in _CLI_FLAG_RE.findall(token):
            refs.add(flag)
    refs.update(_CLI_FLAG_RE.findall(prose))
    refs.update(_UPPER_SNAKE_RE.findall(prose))
    refs.update(_CALLED_NAME_RE.findall(prose))
    # drop trivial noise
    return sorted(r for r in refs if len(r) > 2)
