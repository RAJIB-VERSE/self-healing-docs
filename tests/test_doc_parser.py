from dochealer.indexing.doc_parser import extract_code_refs, parse_docs, parse_markdown


def test_parses_fixture_docs(settings):
    sections = parse_docs(settings)
    ids = {s.id for s in sections}
    assert "docs/guide.md#sample-project" in ids
    assert "docs/guide.md#sample-project-configuration-retries" in ids


def test_heading_paths_nest(settings):
    sections = {s.id: s for s in parse_docs(settings)}
    retries = sections["docs/guide.md#sample-project-configuration-retries"]
    assert retries.heading_path == ("Sample project", "Configuration", "Retries")
    assert retries.level == 3


def test_code_refs_extracted(settings):
    sections = {s.id: s for s in parse_docs(settings)}
    retries = sections["docs/guide.md#sample-project-configuration-retries"]
    assert "Settings" in retries.code_refs
    assert "retry_delay" in retries.code_refs
    assert "reload" in retries.code_refs
    usage = sections["docs/guide.md#sample-project-usage"]
    assert "get_user" in usage.code_refs
    assert "delete_user" in usage.code_refs


def test_unrelated_section_has_no_relevant_refs(settings):
    sections = {s.id: s for s in parse_docs(settings)}
    unrelated = sections["docs/guide.md#sample-project-unrelated-section"]
    assert unrelated.code_refs == []


def test_heading_inside_code_fence_ignored():
    text = "# Real\n\n```\n# not a heading\n```\n\ncontent\n"
    sections = parse_markdown(text, "x.md")
    assert [s.heading_path for s in sections] == [("Real",)]


def test_intro_section_before_first_heading():
    text = "prologue line\n\n# First\n\nbody\n"
    sections = parse_markdown(text, "x.md")
    assert sections[0].heading_path == ("(intro)",)
    assert sections[1].heading_path == ("First",)


def test_extract_refs_variants():
    refs = extract_code_refs(
        "Use `run_sync()` with `--dry-run`. Set MAX_RETRIES. Call cleanup() often."
    )
    assert {"run_sync", "--dry-run", "MAX_RETRIES", "cleanup"} <= set(refs)


def test_line_numbers_track_source():
    text = "# A\n\none\n\n## B\n\ntwo\n"
    sections = parse_markdown(text, "x.md")
    a, b = sections
    assert (a.lineno, a.end_lineno) == (1, 4)
    assert (b.lineno, b.end_lineno) == (5, 7)
