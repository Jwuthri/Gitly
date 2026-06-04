"""CLI surface tests for `gitly lens` (engine wired to the terminal) and `gitly init`
(hook installer). Driven through Typer's CliRunner, so they exercise argument parsing,
exit codes, and output exactly as a user would hit them."""
from __future__ import annotations

import json
import subprocess

from typer.testing import CliRunner

from backend.app.cli import app

runner = CliRunner()

# A substitution applied in two files — the lens engine should fold it into one cluster.
RENAME_DIFF = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,2 +1,2 @@
-x = old_name(1)
+x = new_name(1)
 y = 2
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,2 +1,2 @@
-z = old_name(3)
+z = new_name(3)
 w = 4
"""


def test_lens_clusters_a_diff_from_stdin():
    r = runner.invoke(app, ["lens", "--sites"], input=RENAME_DIFF)
    assert r.exit_code == 0, r.output
    assert "2 files" in r.output and "clusters" in r.output
    assert "site" in r.output                       # rendered the cluster scope
    assert "a.py" in r.output and "b.py" in r.output  # --sites listed the locations


def test_lens_reads_a_file(tmp_path):
    p = tmp_path / "change.diff"
    p.write_text(RENAME_DIFF)
    r = runner.invoke(app, ["lens", str(p)])
    assert r.exit_code == 0, r.output
    assert "clusters" in r.output


def test_lens_json_is_valid(tmp_path):
    p = tmp_path / "change.diff"
    p.write_text(RENAME_DIFF)
    r = runner.invoke(app, ["lens", str(p), "--json"])
    assert r.exit_code == 0, r.output
    data = json.loads(r.output)
    assert "clusters" in data and data["stats"]["files_changed"] == 2


def test_lens_empty_input_errors():
    r = runner.invoke(app, ["lens"], input="")
    assert r.exit_code == 1
    assert "No diff" in r.output


def test_init_installs_executable_hook(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    r = runner.invoke(app, ["init", "--repo", str(tmp_path)])
    assert r.exit_code == 0, r.output
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    assert hook.exists()
    assert hook.stat().st_mode & 0o111            # executable
    assert "gitly" in hook.read_text()


def test_init_errors_outside_a_repo(tmp_path):
    r = runner.invoke(app, ["init", "--repo", str(tmp_path)])
    assert r.exit_code == 1
    assert "Not a git repository" in r.output


def test_init_guards_foreign_hook_then_force_backs_up(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho mine\n")       # a pre-existing, non-gitly hook

    blocked = runner.invoke(app, ["init", "--repo", str(tmp_path)])
    assert blocked.exit_code == 1 and "already exists" in blocked.output
    assert "echo mine" in hook.read_text()          # untouched without --force

    forced = runner.invoke(app, ["init", "--repo", str(tmp_path), "--force"])
    assert forced.exit_code == 0, forced.output
    assert "gitly" in hook.read_text()              # replaced
    assert (tmp_path / ".git" / "hooks" / "pre-commit.bak").read_text() == "#!/bin/sh\necho mine\n"


def test_init_claude_code_registers_hook(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    r = runner.invoke(app, ["init", "--repo", str(tmp_path), "--claude-code"])
    assert r.exit_code == 0, r.output
    settings = tmp_path / ".claude" / "settings.json"
    assert settings.exists()
    data = json.loads(settings.read_text())
    cmds = [h["command"] for e in data["hooks"]["PostToolUse"] for h in e["hooks"]]
    assert any("claude_post_tool.py" in c for c in cmds)
