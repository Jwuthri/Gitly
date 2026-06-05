"""Per-slice validation: run a command against each slice's cumulative tree and flag the
red ones (a slice that doesn't build/test on its own means the ordering shipped something
too late)."""
from __future__ import annotations

import subprocess

from backend.app.engines.shrink.planner.planner import PlanOptions
from backend.app.engines.shrink.service import shrink
from backend.app.engines.shrink.validate import validate_stack


def _git(cwd, *a) -> None:
    subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True)


def _stack_repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "checkout", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@t.co")
    _git(tmp_path, "config", "user.name", "tester")
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "a.py").write_text("a = 1\n")
    (tmp_path / "package.json").write_text('{"x": 1}\n')
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (tmp_path / "src" / "a.py").write_text("a = 1\n" + "\n".join(f"x{i} = 1" for i in range(40)) + "\n")
    (tmp_path / "src" / "b.py").write_text("\n".join(f"y{i} = 2" for i in range(40)) + "\n")
    (tmp_path / "tests" / "t.py").write_text("t = 1\n")
    (tmp_path / "package.json").write_text('{"x": 2}\n')
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "big change")
    return str(tmp_path)


def test_validate_stack_flags_red_and_green(tmp_path):
    repo = _stack_repo(tmp_path)
    res = shrink(repo, "main", "feature",
                 opts=PlanOptions(max_lines=120, min_lines=1, max_slices=20), write_refs=True)
    assert res.completeness_ok and res.materialized and len(res.materialized.slices) >= 2

    # a check that only passes once tests/t.py exists (the test slice is ordered last)
    checks = validate_stack(repo, res, "test -f tests/t.py")
    assert checks[-1].ok, "final slice (with tests/) should pass"
    assert any(not c.ok for c in checks), "an earlier slice lacks tests/ → flagged red"
    assert all(c.order >= 1 for c in checks)

    # an always-green check → every slice passes
    assert all(c.ok for c in validate_stack(repo, res, "true"))
