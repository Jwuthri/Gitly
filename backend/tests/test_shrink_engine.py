from __future__ import annotations

import subprocess

from backend.app.engines.shrink.diff.materialize import validate_partition
from backend.app.engines.shrink.diff.parse import parse_patch_text
from backend.app.engines.shrink.planner.planner import PlanOptions, plan as make_plan
from backend.app.engines.shrink.service import shrink

DIFF = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,2 +1,2 @@
-x = 1
+x = 2
 y = 3
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,1 +1,1 @@
-def f(): return 1
+def f(): return 2
"""


def test_plan_is_a_clean_partition_of_the_diff():
    diff = parse_patch_text(DIFF, "base", "head", "base", "head")
    p = make_plan(diff, PlanOptions(max_lines=400))
    validate_partition(diff, p)  # raises PartitionError if a hunk is missing or duplicated
    assert len(p.slices) >= 1
    assert sum(len(s.hunk_ids) for s in p.slices) == len(diff.all_hunks())


def _git(d, *a):
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


def test_shrink_materializes_a_complete_stack(tmp_path):
    d = tmp_path
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "t@t")
    _git(d, "config", "user.name", "t")
    (d / "src").mkdir()
    (d / "src/auth.py").write_text("def login(u):\n    return token(u)\n")
    (d / "README.md").write_text("# proj\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "base")
    base = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    (d / "src/auth.py").write_text("def login(u):\n    validate(u)\n    return issue_token(u)\n")
    (d / "README.md").write_text("# proj\n\ndocs\n")
    (d / "tests").mkdir()
    (d / "tests/test_auth.py").write_text("def test_x():\n    assert True\n")
    _git(d, "add", "-A")
    _git(d, "commit", "-qm", "head")
    head = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    res = shrink(str(d), base, head, opts=PlanOptions(max_lines=50), prefer_llm=False)
    assert res.completeness_ok  # tree(base + slices) == tree(head)
    assert len(res.slices) >= 2
    assert res.materialized.completeness.final_tree == res.materialized.completeness.head_tree
