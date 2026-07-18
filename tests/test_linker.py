from dochealer.config import INDEX_VERSION
from dochealer.indexing.code_parser import parse_repo
from dochealer.indexing.doc_parser import parse_docs
from dochealer.indexing.linker import build_graph, heuristic_links, load_graph, save_graph


def test_heuristic_links_fixture(settings):
    chunks = parse_repo(settings)
    sections = parse_docs(settings)
    links = heuristic_links(chunks, sections)
    pairs = {(ln.doc_id, ln.chunk_id) for ln in links}
    assert ("docs/guide.md#sample-project-usage", "src/app.py::get_user") in pairs
    assert ("docs/guide.md#sample-project-configuration-retries", "src/app.py::Settings") in pairs
    # constants link too (regression: Timeouts section had zero links before v2)
    assert (
        "docs/guide.md#sample-project-configuration-timeouts",
        "src/app.py::DEFAULT_TIMEOUT",
    ) in pairs
    # unrelated section links to nothing
    assert not any(d == "docs/guide.md#sample-project-unrelated-section" for d, _ in pairs)


def test_graph_lookup(settings):
    chunks = parse_repo(settings)
    sections = parse_docs(settings)
    graph = build_graph(chunks, sections, settings)
    affected = graph.sections_for_chunk("src/app.py::get_user")
    assert any(s.heading_path[-1] == "Usage" for s in affected)


def test_embedding_links_added(settings, fake_embedder):
    settings.similarity_threshold = 0.9
    chunks = parse_repo(settings)
    sections = parse_docs(settings)
    graph = build_graph(chunks, sections, settings, embedder=fake_embedder)
    sources = {ln.source for ln in graph.links}
    assert "heuristic" in sources
    assert "embedding" in sources  # fake vectors overlap on keywords


def test_save_and_load_roundtrip(settings, tmp_path):
    graph = build_graph(parse_repo(settings), parse_docs(settings), settings)
    path = tmp_path / "index.json"
    save_graph(graph, path)
    loaded = load_graph(path)
    assert loaded is not None
    assert loaded.version == INDEX_VERSION
    assert {c.id for c in loaded.chunks} == {c.id for c in graph.chunks}


def test_load_rejects_stale_version(settings, tmp_path):
    graph = build_graph(parse_repo(settings), parse_docs(settings), settings)
    graph.version = INDEX_VERSION + 99
    path = tmp_path / "index.json"
    save_graph(graph, path)
    assert load_graph(path) is None


def test_load_missing_returns_none(tmp_path):
    assert load_graph(tmp_path / "nope.json") is None
