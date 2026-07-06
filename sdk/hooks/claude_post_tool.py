#!/usr/bin/env python3
"""Claude Code PostToolUse hook — record AI authorship provenance after an Edit/Write.

Register in .claude/settings.json:

  "hooks": {
    "PostToolUse": [
      { "matcher": "Edit|Write|MultiEdit",
        "hooks": [ { "type": "command", "command": "python3 sdk/hooks/claude_post_tool.py" } ] }
    ]
  }

Reads the hook JSON from stdin, extracts the edited file + new content, and appends a
redacted provenance event to the local ledger that `gitly trace` reads. Line ranges are
approximate at capture time; the post-commit bind step refines them via blame.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# make gitly_sdk importable whether installed or vendored alongside this file
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
try:
    from gitly_sdk.provenance import record_authorship
except Exception:
    sys.exit(0)  # never block the agent on a provenance failure


def _line_count(text: str) -> int:
    return max(1, text.count("\n") + (0 if text.endswith("\n") else 1))


def _span_in_file(file_path: str, text: str) -> tuple[int, int] | None:
    """Locate `text` in the just-edited file → real (line_start, line_end). The hook runs
    post-edit, so the new text is on disk. First occurrence wins if it appears twice."""
    if not text:
        return None
    try:
        body = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    idx = body.find(text)
    if idx < 0:
        return None
    start = body.count("\n", 0, idx) + 1
    return start, start + _line_count(text) - 1


def _record(payload: dict, file_path: str, new_text: str) -> None:
    span = _span_in_file(file_path, new_text) or (1, _line_count(new_text))
    record_authorship(
        file_path=file_path,
        line_start=span[0],
        line_end=span[1],
        proposed_text=new_text,
        model=payload.get("model"),   # the model Claude Code reports; None if it doesn't (don't guess)
        agent="claude_code",
        session_id=payload.get("session_id"),
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return
    if payload.get("tool_name", "") not in ("Edit", "Write", "MultiEdit"):
        return
    ti = payload.get("tool_input", {}) or {}
    file_path = ti.get("file_path") or ti.get("path") or ""
    if not file_path:
        return
    if payload.get("tool_name") == "MultiEdit":   # one event per applied edit
        for edit in ti.get("edits") or []:
            text = (edit or {}).get("new_string") or ""
            if text:
                _record(payload, file_path, text)
        return
    new_text = ti.get("new_string") or ti.get("content") or ""
    if new_text:
        _record(payload, file_path, new_text)


if __name__ == "__main__":
    main()
