from dochealer.indexing.code_parser import parse_repo, parse_source


def test_parses_fixture_repo(settings):
    chunks = parse_repo(settings)
    ids = {c.id for c in chunks}
    assert "src/app.py::get_user" in ids
    assert "src/app.py::Settings" in ids
    assert "src/app.py::Settings.reload" in ids
    assert "src/app.py::_internal_helper" in ids


def test_function_metadata(settings):
    chunks = {c.id: c for c in parse_repo(settings)}
    fn = chunks["src/app.py::get_user"]
    assert fn.kind == "function"
    assert fn.signature == "def get_user(user_id: int, include_inactive: bool=False) -> dict"
    assert "Fetch a user by ID" in fn.docstring
    assert fn.source.startswith("def get_user")
    assert fn.lineno < fn.end_lineno


def test_method_qualname(settings):
    chunks = {c.id: c for c in parse_repo(settings)}
    method = chunks["src/app.py::Settings.reload"]
    assert method.kind == "method"
    assert method.name == "reload"
    assert method.qualname == "Settings.reload"


def test_class_chunk(settings):
    chunks = {c.id: c for c in parse_repo(settings)}
    cls = chunks["src/app.py::Settings"]
    assert cls.kind == "class"
    assert cls.signature == "class Settings"
    assert "retry_delay" in cls.source


def test_unparseable_source_is_skipped():
    assert parse_source("def broken(:\n", "bad.py") == []


def test_cli_decorator_detection():
    source = (
        "import click\n\n"
        "@click.command()\n"
        "def sync(force: bool = False):\n"
        '    """Sync things."""\n'
    )
    chunks = parse_source(source, "cli.py")
    assert len(chunks) == 1
    assert chunks[0].kind == "cli"


def test_module_constants_extracted(settings):
    chunks = {c.id: c for c in parse_repo(settings)}
    const = chunks["src/app.py::DEFAULT_TIMEOUT"]
    assert const.kind == "config"
    assert const.signature == "DEFAULT_TIMEOUT = 30"


def test_constant_variants():
    source = (
        "MAX_RETRIES: int = 3\n"        # annotated
        "API_URL = 'https://x'\n"        # plain
        "lowercase = 1\n"                # not a constant
        "X = 2\n"                        # single letter still UPPER_SNAKE
        "A, B = 1, 2\n"                  # tuple unpacking: skipped
    )
    chunks = {c.name: c for c in parse_source(source, "consts.py")}
    assert {"MAX_RETRIES", "API_URL", "X"} <= set(chunks)
    assert "lowercase" not in chunks
    assert "A" not in chunks and "B" not in chunks
    assert chunks["MAX_RETRIES"].kind == "config"
