"""Copilot git operations — safe staging, secret-block, protected-branch, split, absorb.

These run real `git` against a throwaway repo (no mocks): the value is in the actual git
behavior. `core.excludesFile=/dev/null` neutralizes the developer's global gitignore so the
safe-add guard — not gitignore — is what's under test. msg_mode='off' keeps messages
deterministic (heuristic, no network)."""
from __future__ import annotations

import subprocess

import pytest

from backend.app.engines.copilot import ops


def _git(cwd, *args) -> str:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    """A fresh git repo on feature branch 'work' with one commit."""
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "checkout", "-q", "-b", "work")
    _git(tmp_path, "config", "user.email", "t@t.co")
    _git(tmp_path, "config", "user.name", "tester")
    _git(tmp_path, "config", "core.excludesFile", "/dev/null")
    (tmp_path / "README.md").write_text("# proj\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "init")
    return tmp_path


def test_safe_commit_skips_risky_files(repo):
    (repo / "app.py").write_text("x = 1\n")
    (repo / ".env").write_text("TOKEN=shhh\n")          # gitly:allow
    (repo / "node_modules").mkdir()
    (repo / "node_modules" / "m.js").write_text("junk\n")
    ok, msg = ops.safe_commit(str(repo), "feat: app", stage_all=True, msg_mode="off")
    assert ok, msg
    tracked = _git(repo, "ls-files").split()
    assert "app.py" in tracked
    assert ".env" not in tracked                         # safe-add refused the secret file
    assert not any(t.startswith("node_modules/") for t in tracked)
    assert "skipped" in msg                              # and it tells you what it skipped


def test_safe_commit_refuses_protected_branch(repo):
    _git(repo, "checkout", "-q", "-b", "main")
    (repo / "app.py").write_text("y = 2\n")
    ok, msg = ops.safe_commit(str(repo), "feat: x", stage_all=True, msg_mode="off")
    assert not ok
    assert "protected" in msg.lower()


def test_safe_commit_blocks_secrets_and_unstages(repo):
    secret = "AKIA1234567890ABCDEF"                      # gitly:allow
    (repo / "config.py").write_text(f'AWS_KEY = "{secret}"\n')
    ok, msg = ops.safe_commit(str(repo), "x", stage_all=True, msg_mode="off")
    assert not ok
    assert "secret" in msg.lower()
    assert _git(repo, "diff", "--cached").strip() == ""  # rolled back — nothing left staged


def test_safe_commit_nothing_to_commit(repo):
    ok, msg = ops.safe_commit(str(repo), "x", msg_mode="off")
    assert not ok
    assert "nothing" in msg.lower()


def test_safe_commit_auto_message_is_conventional(repo):
    (repo / "README.md").write_text("# proj\n\nmore docs\n")
    ok, msg = ops.safe_commit(str(repo), None, msg_mode="off")
    assert ok, msg
    subject = _git(repo, "log", "-1", "--format=%s").strip()
    assert ":" in subject and subject.split(":")[0] in {"feat", "fix", "docs", "test", "chore", "refactor"}


def test_split_groups_by_category(repo):
    (repo / "app.py").write_text("x = 1\n")
    (repo / "test_app.py").write_text("def test_x():\n    assert True\n")
    (repo / "guide.md").write_text("# guide\n")
    (repo / "pyproject2.toml").write_text("[tool]\n")
    ok, lines = ops.split_commit(str(repo), stage_all=True, msg_mode="off")
    assert ok
    body = "\n".join(lines)
    # one commit per concern, each with a conventional type
    commits = len(_git(repo, "log", "--oneline").splitlines())
    assert commits >= 1 + 3                              # init + at least 3 grouped commits
    assert "test:" in body and "docs:" in body


def test_absorb_folds_into_earlier_commit(repo):
    (repo / "foo.py").write_text("a = 1\n")
    _git(repo, "add", "foo.py")
    _git(repo, "commit", "-qm", "feat: foo")
    (repo / "bar.py").write_text("b = 2\n")
    _git(repo, "add", "bar.py")
    _git(repo, "commit", "-qm", "feat: bar")
    before = len(_git(repo, "log", "--oneline").splitlines())

    (repo / "foo.py").write_text("a = 1\nc = 3\n")        # a follow-up that belongs in 'feat: foo'
    ok, msg = ops.absorb(str(repo))
    assert ok, msg
    assert len(_git(repo, "log", "--oneline").splitlines()) == before  # folded, no new commit
    assert _git(repo, "status", "--porcelain").strip() == ""           # clean tree
    foo_commit = _git(repo, "log", "-1", "--format=%H", "--", "foo.py").strip()
    assert "c = 3" in _git(repo, "show", foo_commit)                   # change landed in foo's commit


def test_diff_vs_head_includes_untracked_and_restores_index(repo):
    (repo / "README.md").write_text("# proj\nmore\n")     # tracked, modified
    (repo / "new.py").write_text("def boom():\n    return 42\n")  # untracked
    before = _git(repo, "status", "--porcelain")
    diff = ops._diff_vs_head(str(repo), ["README.md", "new.py"])
    assert "def boom" in diff                             # untracked content is included…
    assert "more" in diff                                 # …alongside the tracked change
    assert _git(repo, "status", "--porcelain") == before  # and the index is restored
