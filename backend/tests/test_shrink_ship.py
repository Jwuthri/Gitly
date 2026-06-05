"""`gitly shrink --pr` shipping layer: a verified stack → ordered, chained PR specs."""
from __future__ import annotations

from backend.app.engines.shrink.diff.completeness import CompletenessResult
from backend.app.engines.shrink.diff.materialize import MaterializeResult, SliceCommit
from backend.app.engines.shrink.service import ShrinkResult
from backend.app.engines.shrink.ship import compare_url, pr_specs


def _result(slices: list[SliceCommit]) -> ShrinkResult:
    return ShrinkResult(
        repo="r", base_ref="main", head_ref="HEAD",
        original_lines=100, original_files=5, strategy="hybrid", slices=[], notes=[],
        materialized=MaterializeResult(
            base_commit="b" * 40, head_commit="h" * 40, final_commit="f" * 40, slices=slices,
            completeness=CompletenessResult(ok=True, final_tree="t" * 40, head_tree="t" * 40),
        ),
    )


def test_pr_specs_chains_the_stack():
    slices = [
        SliceCommit(order=1, title="chore: deps", commit_sha="1" * 40, branch="shrink/1-deps", base_branch="main"),
        SliceCommit(order=2, title="feat: core", commit_sha="2" * 40, branch="shrink/2-core", base_branch="shrink/1-deps"),
        SliceCommit(order=3, title="test: cover", commit_sha="3" * 40, branch="shrink/3-cover", base_branch="shrink/2-core"),
    ]
    specs = pr_specs(_result(slices))
    # each slice's PR is based on the previous slice's branch — a real stack
    assert [s["branch"] for s in specs] == ["shrink/1-deps", "shrink/2-core", "shrink/3-cover"]
    assert [s["base"] for s in specs] == ["main", "shrink/1-deps", "shrink/2-core"]
    assert specs[0]["title"] == "chore: deps"
    assert "stack" in specs[0]["body"]


def test_pr_specs_skips_unmaterialized_and_empty():
    # a slice without a branch is skipped
    s = SliceCommit(order=1, title="x", commit_sha="1" * 40, branch=None, base_branch="main")
    assert pr_specs(_result([s])) == []
    # no materialization → nothing to ship
    r = ShrinkResult(repo="r", base_ref="main", head_ref="HEAD", original_lines=0,
                     original_files=0, strategy="hybrid", slices=[], notes=[], materialized=None)
    assert pr_specs(r) == []


def test_compare_url():
    assert compare_url("o/r", "main", "shrink/1-x") == "https://github.com/o/r/compare/main...shrink/1-x?expand=1"
