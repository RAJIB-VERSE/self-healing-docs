from dochealer.detection.change_filter import filter_meaningful, is_meaningful, is_test_file
from dochealer.models import ChangedChunk


def make(chunk_id="src/app.py::fn", kind="modified", old="", new="", old_sig="", new_sig=""):
    return ChangedChunk(
        chunk_id=chunk_id, change_kind=kind,
        old_source=old, new_source=new, old_signature=old_sig, new_signature=new_sig,
    )


def test_test_files_detected():
    assert is_test_file("tests/test_app.py")
    assert is_test_file("src/foo_test.py")
    assert is_test_file("tests/conftest.py")
    assert not is_test_file("src/app.py")


def test_test_file_changes_dropped():
    assert not is_meaningful(make(chunk_id="tests/test_app.py::test_x", kind="added"))


def test_private_chunks_dropped():
    assert not is_meaningful(make(chunk_id="src/app.py::_helper", kind="modified",
                                  old="def _helper(): return 1", new="def _helper(): return 2"))
    assert not is_meaningful(make(chunk_id="src/app.py::Cls._private", kind="modified",
                                  old="def _private(self): ...", new="def _private(self): pass"))


def test_added_and_removed_public_kept():
    assert is_meaningful(make(kind="added", new="def fn(): pass"))
    assert is_meaningful(make(kind="removed", old="def fn(): pass"))


def test_signature_change_kept():
    change = make(
        old="def fn(a):\n    return a", new="def fn(a, b=1):\n    return a",
        old_sig="def fn(a)", new_sig="def fn(a, b=1)",
    )
    assert is_meaningful(change)


def test_comment_only_change_dropped():
    change = make(
        old="def fn(a):\n    # old comment\n    return a",
        new="def fn(a):\n    # new comment\n    return a",
        old_sig="def fn(a)", new_sig="def fn(a)",
    )
    assert not is_meaningful(change)


def test_docstring_only_change_dropped():
    change = make(
        old='def fn(a):\n    """Old docs."""\n    return a',
        new='def fn(a):\n    """New docs."""\n    return a',
        old_sig="def fn(a)", new_sig="def fn(a)",
    )
    assert not is_meaningful(change)


def test_whitespace_only_change_dropped():
    change = make(
        old="def fn(a):\n    return a",
        new="def fn(a):\n\n    return  a",
        old_sig="def fn(a)", new_sig="def fn(a)",
    )
    assert not is_meaningful(change)


def test_behavior_change_kept():
    change = make(
        old="def fn(a):\n    return a * 2",
        new="def fn(a):\n    return a * 3",
        old_sig="def fn(a)", new_sig="def fn(a)",
    )
    assert is_meaningful(change)


def test_filter_meaningful_list():
    keep = make(kind="added", new="def fn(): pass")
    drop = make(chunk_id="tests/test_x.py::t", kind="added")
    assert filter_meaningful([keep, drop]) == [keep]
