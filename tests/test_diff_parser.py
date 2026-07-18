from dochealer.detection.diff_parser import changed_python_files, compare_versions

DIFF = """\
diff --git a/src/app.py b/src/app.py
index 111..222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -8,1 +8,1 @@ def get_user
-def get_user(user_id: int, include_inactive: bool = False) -> dict:
+def get_user(user_id: int, active_only: bool = True) -> dict:
@@ -20 +20,2 @@
+    extra = 1
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-old
+new
diff --git a/src/gone.py b/src/gone.py
deleted file mode 100644
--- a/src/gone.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def bye():
-    pass
"""


def test_changed_files_filters_to_python():
    files = changed_python_files(DIFF)
    assert "src/app.py" in files
    assert "README.md" not in files


def test_hunk_ranges_parsed():
    files = changed_python_files(DIFF)
    assert (8, 8) in files["src/app.py"]
    assert (20, 21) in files["src/app.py"]


def test_deleted_file_tracked():
    files = changed_python_files(DIFF)
    assert "src/gone.py" in files


OLD = '''\
def get_user(user_id: int) -> dict:
    """Fetch."""
    return {"id": user_id}


def unchanged() -> None:
    pass
'''

NEW = '''\
def get_user(user_id: int, active_only: bool = True) -> dict:
    """Fetch."""
    return {"id": user_id, "active": active_only}


def unchanged() -> None:
    pass


def brand_new() -> str:
    return "hi"
'''


def test_compare_versions_classifies():
    changes = {c.chunk_id: c for c in compare_versions("src/app.py", OLD, NEW, [(1, 3), (9, 10)])}
    assert changes["src/app.py::get_user"].change_kind == "modified"
    assert changes["src/app.py::brand_new"].change_kind == "added"
    assert "src/app.py::unchanged" not in changes


def test_compare_versions_detects_removal():
    changes = compare_versions("src/app.py", OLD, "", [])
    kinds = {c.chunk_id: c.change_kind for c in changes}
    assert kinds["src/app.py::get_user"] == "removed"


def test_signatures_captured():
    changes = {c.chunk_id: c for c in compare_versions("src/app.py", OLD, NEW, [(1, 3)])}
    ch = changes["src/app.py::get_user"]
    assert "user_id: int" in ch.old_signature
    assert "active_only" in ch.new_signature
