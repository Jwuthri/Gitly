#!/usr/bin/env python3
"""Seed the gitly backend with realistic AI-authorship provenance.

Structured as real files with contiguous, content-carrying spans, so the trace
file-tree + per-line blame render actual code colored by author. Stdlib only;
idempotent (stable record ids -> re-running upserts).

  python3 scripts/seed_demo.py [--repo demo-app] [--api http://localhost:8000]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request

H, AI, HY = "human", "ai", "hybrid"

# Each file = an ordered list of contiguous spans. A span carries who wrote it and the
# actual code lines (so the blame view shows real code).
FILES: list[tuple[str, list[dict]]] = [
    ("src/auth/session.py", [
        {"who": H, "lines": ["import time", "from .store import Store", "", "class SessionStore:",
                             "    def __init__(self, redis):", "        self._redis = redis"]},
        {"who": AI, "model": "gpt-4o", "agent": "copilot", "reviewed": False,
         "prompt": "Add get() that reads a session from Redis and decodes it",
         "lines": ["", "    def get(self, sid):", "        raw = self._redis.get(sid)",
                   "        return decode(raw) if raw else None"]},
        {"who": HY, "model": "claude-sonnet-4-6", "agent": "cursor", "edit": 0.55,
         "prompt": "Implement refresh() with an expiry check and re-persist",
         "lines": ["", "    def refresh(self, sid):", "        s = self.get(sid)",
                   "        if not s or s.expired():", "            raise SessionExpired(sid)",
                   "        s.touch()", "        self._redis.set(sid, encode(s))", "        return s"]},
        {"who": H, "lines": ["", "    def drop(self, sid):", "        self._redis.delete(sid)"]},
    ]),
    ("src/auth/login.py", [
        {"who": H, "lines": ["from .session import SessionStore", "", "def login(user, pw):"]},
        {"who": AI, "model": "claude-opus-4-8", "agent": "claude_code", "reviewed": False,
         "prompt": "Verify credentials and issue a token",
         "lines": ["    if not verify(user, pw):", "        raise BadCredentials()", "    token = issue_token(user)"]},
        {"who": HY, "model": "claude-opus-4-8", "agent": "claude_code", "edit": 0.72, "reviewed": False,
         "prompt": "Persist the token and write an audit log line",
         "lines": ["    store.persist(token)", "    audit('login', user)", "    return token"]},
    ]),
    ("src/api/routes.py", [
        {"who": H, "lines": ["from fastapi import APIRouter", "", "router = APIRouter()"]},
        {"who": AI, "model": "claude-sonnet-4-6", "agent": "cursor", "reviewed": True,
         "prompt": "Add the POST /login route",
         "lines": ["", "@router.post('/login')", "async def login_route(body):", "    return await do_login(body)"]},
        {"who": AI, "model": "claude-sonnet-4-6", "agent": "cursor", "reviewed": False,
         "prompt": "Add a POST /logout route mirroring login",
         "lines": ["", "@router.post('/logout')", "async def logout_route(body):", "    return await do_logout(body)"]},
    ]),
    ("src/db/models.py", [
        {"who": H, "lines": ["from sqlalchemy import Column, String, DateTime", "", "class User(Base):",
                             "    id = Column(String, primary_key=True)"]},
        {"who": HY, "model": "gpt-4o", "agent": "copilot", "edit": 0.6, "reviewed": False,
         "prompt": "Add email, created_at and last_login columns",
         "lines": ["    email = Column(String, unique=True)", "    created_at = Column(DateTime, default=now)",
                   "    last_login = Column(DateTime, nullable=True)"]},
    ]),
    ("web/components/Button.tsx", [
        {"who": H, "lines": ["import React, { useState } from 'react';", "", "export function Button({ label, onClick }) {"]},
        {"who": AI, "model": "claude-opus-4-8", "agent": "claude_code", "reviewed": True,
         "prompt": "Add a busy state so the button disables while the action runs",
         "lines": ["  const [busy, setBusy] = useState(false);",
                   "  const run = async () => { setBusy(true); await onClick(); setBusy(false); };"]},
        {"who": AI, "model": "gemini-2.0-pro", "agent": "cursor", "reviewed": True,
         "prompt": "Render the button using the disabled state",
         "lines": ["  return <button disabled={busy} onClick={run}>{busy ? '…' : label}</button>;", "}"]},
    ]),
    ("README.md", [
        {"who": HY, "model": "claude-opus-4-8", "agent": "claude_code", "edit": 0.74, "reviewed": True,
         "prompt": "Write a short intro for the project README",
         "lines": ["# acme", "", "A small API with Redis-backed sessions and audited logins.", "",
                   "## Setup", "Run with `docker compose up`."]},
        {"who": AI, "model": "claude-sonnet-4-6", "agent": "cursor", "reviewed": True,
         "prompt": "Document the auth API routes",
         "lines": ["", "## API", "- `POST /login`", "- `POST /logout`"]},
    ]),
]

REVIEWERS = ["alice", "bob", "carol", "dan"]


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def build_records(repo: str) -> list[dict]:
    out: list[dict] = []
    today = time.strftime("%Y-%m-%d")
    for fi, (path, spans) in enumerate(FILES):
        cursor = 1
        for si, sp in enumerate(spans):
            who, lines = sp["who"], sp["lines"]
            ls, le = cursor, cursor + len(lines) - 1
            cursor += len(lines)
            is_ai = who in (AI, HY)
            reviewed = sp.get("reviewed", True)
            prompt = sp.get("prompt") if is_ai else None
            reviewer = REVIEWERS[(fi + si) % len(REVIEWERS)] if reviewed else None
            ts = f"{today}T1{fi}:0{si % 6}:00"
            out.append({
                "record_id": _sha(f"{repo}:{path}:{ls}")[:32],
                "repo": repo,
                "commit_sha": hashlib.sha1(f"{path}:{ls}".encode()).hexdigest(),
                "file_path": path,
                "line_start": ls,
                "line_end": le,
                "author_type": who,
                "model": sp.get("model") if is_ai else None,
                "agent": sp.get("agent", "unknown") if is_ai else "unknown",
                "session_id": f"sess-{fi}{si}",
                "prompt_ref": _sha(prompt)[:16] if prompt else None,
                "prompt_redacted": prompt,
                "content": "\n".join(lines),
                "human_edit_ratio": sp.get("edit", 0.0 if who == H else (0.12 if who == AI else 0.5)),
                "reviewed_by": reviewer,
                "reviewed_at": ts if reviewer else None,
                "created_at": ts,
                "bound_at": ts,
            })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="demo-app")
    ap.add_argument("--api", default="http://localhost:8000")
    args = ap.parse_args()

    records = build_records(args.repo)
    url = f"{args.api.rstrip('/')}/trace/records"
    req = urllib.request.Request(url, data=json.dumps(records).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise SystemExit(f"Could not reach {url} — is the backend running (make up)? ({e})")

    print(f"Seeded {result.get('ingested', len(records))} spans across {len(FILES)} files into '{args.repo}'.")
    print(f"  Dashboard: http://localhost:3000/trace?repo={args.repo}")


if __name__ == "__main__":
    main()
