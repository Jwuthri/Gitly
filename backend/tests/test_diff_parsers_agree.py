"""Three diff parsers exist today (shared kernel facade, lens's line-level parser, shrink's
unidiff wrapper) — see MIGRATION.md, which plans to merge them. Until that happens, this is
the drift tripwire: all three must agree on the basics for the same diff."""
from __future__ import annotations

from backend.app.engines.lens.diff.parser import parse_diff as lens_parse
from backend.app.engines.shrink.diff.parse import parse_patch_text as shrink_parse
from shared.diff_core.parser import parse_unified_diff as kernel_parse

DIFF = """\
diff --git a/src/app.py b/src/app.py
index 1111111..2222222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,5 @@
 import os
-def old():
-    return 1
+def new():
+    return 2
+# extra
 print("x")
diff --git a/docs/new.md b/docs/new.md
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/docs/new.md
@@ -0,0 +1,2 @@
+# title
+body
"""

PATHS = {"src/app.py", "docs/new.md"}


def test_all_three_parsers_see_the_same_files_and_hunks():
    kernel = kernel_parse(DIFF)
    lens = lens_parse(DIFF)
    shrink = shrink_parse(DIFF, "base", "head", "base", "head")

    assert {f.path for f in kernel.files} == PATHS
    assert {f.path for f in lens.files} == PATHS
    assert {f.path for f in shrink.files} == PATHS

    assert [len(f.hunks) for f in kernel.files] == [1, 1]
    assert [len(f.hunks) for f in lens.files] == [1, 1]
    assert [len(f.hunks) for f in shrink.files] == [1, 1]


def test_lens_and_shrink_agree_on_line_counts():
    lens = {f.path: (f.additions, f.deletions) for f in lens_parse(DIFF).files}
    shrink = {f.path: (f.added, f.removed) for f in shrink_parse(DIFF, "b", "h", "b", "h").files}
    assert lens == shrink == {"src/app.py": (3, 2), "docs/new.md": (2, 0)}
