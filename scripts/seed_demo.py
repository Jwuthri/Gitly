#!/usr/bin/env python3
"""Seed the gitly backend with realistic fake AI-authorship provenance so you can see
the `trace` dashboard populated.

POSTs a batch of ProvenanceRecords to the running backend (POST /trace/records), then
open http://localhost:3000/trace?repo=<repo> to view them. Stdlib only — no deps.
Idempotent: a fixed --seed produces stable record_ids, so re-running upserts (no dupes).

Usage:
  python3 scripts/seed_demo.py                          # repo=demo-app, 60 records
  python3 scripts/seed_demo.py --repo my-app --count 80
  python3 scripts/seed_demo.py --api http://localhost:8000
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

FILES = [
    "src/auth/login.py", "src/auth/session.py", "src/api/routes.py",
    "src/db/models.py", "src/utils/format.py", "web/components/Button.tsx",
    "web/pages/index.tsx", "tests/test_auth.py", "README.md",
]

# (model, agent) pairs — a believable mix of who wrote what
MODELS = [
    ("claude-opus-4-8", "claude_code"),
    ("claude-sonnet-4-6", "claude_code"),
    ("claude-sonnet-4-6", "cursor"),
    ("gpt-4o", "copilot"),
    ("gpt-4o", "cursor"),
    ("gemini-2.0-pro", "cursor"),
]

PROMPTS = [
    "Implement JWT login with refresh tokens",
    "Add rate limiting to the API routes",
    "Refactor the session store to use Redis",
    "Write unit tests for the auth module",
    "Fix the date formatting helper for timezones",
    "Add a loading state to the Button component",
    "Paginate the index page results",
    "Add type hints to the db models",
    # a planted secret — the ingest endpoint redacts it server-side before storing:
    "Call the billing API with key sk-ant-api03-Abc123Def456Ghi789Jkl012Mno345",
]

REVIEWERS = ["alice", "bob", "carol", "dan"]


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def make_records(repo: str, count: int, rng: random.Random) -> list[dict]:
    now = datetime.now(timezone.utc)
    records: list[dict] = []
    for i in range(count):
        path = rng.choice(FILES)
        roll = rng.random()
        if roll < 0.25:                       # ~25% human
            author_type, model, agent, ratio = "human", None, "unknown", 0.0
        elif roll < 0.70:                     # ~45% AI (lightly edited at most)
            model, agent = rng.choice(MODELS)
            author_type, ratio = "ai", round(rng.uniform(0.0, 0.35), 2)
        else:                                 # ~30% hybrid (materially human-edited)
            model, agent = rng.choice(MODELS)
            author_type, ratio = "hybrid", round(rng.uniform(0.5, 0.85), 2)

        start = rng.randint(1, 180)
        span = rng.randint(1, 40)
        created = now - timedelta(days=rng.randint(0, 13), hours=rng.randint(0, 23))

        # ~45% of AI/hybrid spans are unreviewed -> lights up the "unreviewed AI" metric
        reviewed_by = (rng.choice(REVIEWERS)
                       if author_type == "human" or rng.random() > 0.45 else None)
        reviewed_at = _iso(created + timedelta(hours=rng.randint(1, 48))) if reviewed_by else None
        prompt = None if author_type == "human" else rng.choice(PROMPTS)

        records.append({
            "record_id": hashlib.sha256(f"{repo}:{path}:{start}:{i}".encode()).hexdigest()[:32],
            "repo": repo,
            "commit_sha": hashlib.sha1(f"{repo}{i}".encode()).hexdigest(),
            "file_path": path,
            "line_start": start,
            "line_end": start + span,
            "author_type": author_type,
            "model": model,
            "agent": agent,
            "session_id": f"sess-{rng.randint(1000, 9999)}",
            "prompt_ref": hashlib.sha256((prompt or '').encode()).hexdigest()[:16] if prompt else None,
            "prompt_redacted": prompt,
            "human_edit_ratio": ratio,
            "reviewed_by": reviewed_by,
            "reviewed_at": reviewed_at,
            "created_at": _iso(created),
            "bound_at": _iso(created + timedelta(minutes=rng.randint(1, 30))),
        })
    return records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="demo-app")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--count", type=int, default=60)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    records = make_records(args.repo, args.count, random.Random(args.seed))
    url = f"{args.api.rstrip('/')}/trace/records"
    req = urllib.request.Request(
        url, data=json.dumps(records).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
    except urllib.error.URLError as e:
        raise SystemExit(f"Could not reach {url} — is the backend running (make up)? ({e})")

    print(f"Seeded {result.get('ingested', len(records))} records into repo '{args.repo}'.")
    print(f"  Dashboard: http://localhost:3000/trace?repo={args.repo}")
    print(f"  API:       {args.api}/trace/summary?repo={args.repo}")


if __name__ == "__main__":
    main()
