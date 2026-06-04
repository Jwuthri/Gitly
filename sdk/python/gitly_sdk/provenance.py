"""gitly-sdk — record AI authorship provenance from a coding agent or git hook.

Dependency-light on purpose: any agent (a Claude Code hook, Cursor, a CI step) can call
`record_authorship()` to append a *redacted* event to the local ledger that `gitly trace`
reads. No network unless you opt into sync. Secrets in prompts/diffs are stripped here,
before anything touches disk — so provenance capture can never become a leak.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

# Minimal inline redaction — mirrors backend.app.security.secret_firewall so the SDK stays
# dependency-free. Keep the two patterns lists in sync.
_PATTERNS = [
    ("aws_access_key_id", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("generic", re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"]([^'\"]{12,})['\"]")),
]


# Agent identifiers the `gitly trace` schema understands; anything else is recorded as
# "unknown" so an arbitrary tool name can never produce an unreadable ledger.
_KNOWN_AGENTS = {"claude_code", "cursor", "copilot", "windsurf", "aider", "unknown"}


def redact(text: str | None) -> str | None:
    if not text:
        return text
    out = text
    for kind, pat in _PATTERNS:
        out = pat.sub(f"‹redacted:{kind}›", out)
    return out


def content_hash(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _repo_root(start: str | None = None) -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start or os.getcwd(), capture_output=True, text=True, check=True,
        )
        return Path(out.stdout.strip())
    except Exception:
        return Path(start or os.getcwd())


def record_authorship(
    file_path: str,
    line_start: int,
    line_end: int,
    *,
    proposed_text: str = "",
    model: str | None = None,
    agent: str = "unknown",   # claude_code | cursor | copilot | windsurf | aider | unknown
    prompt: str | None = None,
    session_id: str | None = None,
    repo_root: str | None = None,
    ledger: str = ".gitly/provenance",
) -> str:
    """Append one redacted authorship event to the local ledger. Returns the event id.
    Call right after an agent applies an edit (e.g. from a PostToolUse hook)."""
    root = _repo_root(repo_root)
    event = {
        "event_id": uuid.uuid4().hex,
        "repo": root.name,
        "file_path": file_path,
        "content_hash": content_hash(proposed_text),
        "line_start": line_start,
        "line_end": line_end,
        "author_type": "ai",
        "model": model,
        "agent": agent if agent in _KNOWN_AGENTS else "unknown",
        "session_id": session_id,
        "prompt_ref": content_hash(prompt)[:16] if prompt else None,
        "prompt_redacted": redact(prompt),
        "proposed_text": redact(proposed_text),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    d = root / ledger
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{time.strftime('%Y-%m-%d')}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")
    return event["event_id"]
