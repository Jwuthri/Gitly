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
    new_text = ti.get("new_string") or ti.get("content") or ""
    record_authorship(
        file_path=file_path,
        line_start=1,
        line_end=max(1, new_text.count("\n") + 1),
        proposed_text=new_text,
        model=payload.get("model"),   # the model Claude Code reports; None if it doesn't (don't guess)
        agent="claude_code",
        session_id=payload.get("session_id"),
    )


if __name__ == "__main__":
    main()
