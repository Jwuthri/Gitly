from __future__ import annotations

from backend.app.engines.lens.engine import analyze, make_source
from backend.app.engines.lens.models import Confidence, SourceType

RENAME = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-x = make_token(a)
+x = issue_token(a)
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,1 +1,1 @@
-y = make_token(b)
+y = issue_token(b)
"""

OUTLIER = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-getUser(1)
+fetchUser(1)
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,1 +1,1 @@
-getUser(2)
+fetchUser(2)
diff --git a/c.py b/c.py
--- a/c.py
+++ b/c.py
@@ -1,1 +1,1 @@
-getUser(3)
+fetchAdmin(3)
"""


def test_rename_collapses_to_one_high_cluster():
    r = analyze(RENAME, make_source(SourceType.raw_diff))
    high = [c for c in r.clusters if c.confidence == Confidence.high]
    assert len(high) == 1
    assert high[0].site_count == 2
    assert high[0].file_count == 2
    assert "make_token" in high[0].title and "issue_token" in high[0].title


def test_partition_every_hunk_in_exactly_one_cluster():
    r = analyze(RENAME, make_source(SourceType.raw_diff))
    seen = [s.hunk_id for c in r.clusters for s in c.sites]
    assert sorted(seen) == sorted(r.hunks.keys())
    assert len(seen) == len(set(seen))  # no hunk in two clusters


def test_minority_substitution_is_flagged_as_outlier():
    r = analyze(OUTLIER, make_source(SourceType.raw_diff))
    high = [c for c in r.clusters if c.confidence == Confidence.high]
    assert len(high) == 1
    assert high[0].site_count == 3
    assert len(high[0].outliers) == 1  # getUser->fetchAdmin deviates from the fetchUser majority
