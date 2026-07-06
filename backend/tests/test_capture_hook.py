"""The Claude Code PostToolUse capture hook must record *real* line spans (located in the
just-edited file, not 1..N) and one event per MultiEdit edit — run as a subprocess, exactly
as Claude Code runs it."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.engines.trace import recorder

HOOK = Path(__file__).resolve().parents[2] / "sdk" / "hooks" / "claude_post_tool.py"


def _git(cwd, *a) -> str:
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    return tmp_path


def _run_hook(repo: Path, payload: dict) -> None:
    subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload), text=True, cwd=repo, check=True, timeout=30,
    )


def test_edit_event_carries_the_real_span_and_relative_path(repo):
    f = repo / "pkg" / "mod.py"
    f.parent.mkdir()
    f.write_text("import os\n\n\ndef added_by_ai():\n    return 1\n")

    _run_hook(repo, {
        "tool_name": "Edit", "session_id": "s1",
        "tool_input": {"file_path": str(f), "new_string": "def added_by_ai():\n    return 1\n"},
    })
    events = recorder.read_events(repo)
    assert len(events) == 1
    assert events[0].file_path == "pkg/mod.py"          # repo-relative, not absolute
    assert (events[0].line_start, events[0].line_end) == (4, 5)   # located, not 1..N


def test_multiedit_records_one_event_per_edit(repo):
    f = repo / "m.py"
    f.write_text("alpha = 1\nkeep = 0\nbeta = 2\n")

    _run_hook(repo, {
        "tool_name": "MultiEdit",
        "tool_input": {"file_path": str(f), "edits": [
            {"old_string": "a0", "new_string": "alpha = 1\n"},
            {"old_string": "b0", "new_string": "beta = 2\n"},
        ]},
    })
    events = recorder.read_events(repo)
    assert len(events) == 2
    spans = sorted((e.line_start, e.line_end) for e in events)
    assert spans == [(1, 1), (3, 3)]


def test_hook_ignores_non_edit_tools_and_empty_text(repo):
    _run_hook(repo, {"tool_name": "Bash", "tool_input": {"command": "ls"}})
    _run_hook(repo, {"tool_name": "Edit", "tool_input": {"file_path": str(repo / "x.py"), "new_string": ""}})
    assert recorder.read_events(repo) == []
