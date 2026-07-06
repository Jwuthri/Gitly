"""Push this repo's REAL provenance (the blame-join `gitly trace` computes) to the backend,
so the web dashboard shows the actual repo instead of seed fixtures.

The CLI reads your local ledger; the dashboard reads Postgres — this bridges the two. Per-line
provenance is grouped into contiguous spans and POSTed to `/trace/records`. Stdlib-only HTTP
so it stays in the lean CLI (no httpx/requests)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from backend.app.engines.trace.blame import trace_file


def _headers() -> dict[str, str]:
    """Content type + optional bearer auth (GITLY_API_KEY) — matches the backend's
    write-guard on POST/DELETE /trace/records."""
    h = {"Content-Type": "application/json"}
    key = os.environ.get("GITLY_API_KEY")
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def origin_repo_key(repo_root: Path) -> str:
    """A stable dashboard key from the git `origin` remote (normalized to https form),
    falling back to the directory name. This is the value to type in the /trace box."""
    try:
        url = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True, timeout=10,
        ).stdout.strip()
    except Exception:
        return repo_root.name
    if url.startswith("git@"):                 # git@github.com:owner/repo.git
        url = "https://" + url[4:].replace(":", "/", 1)
    if url.endswith(".git"):
        url = url[:-4]
    return url or repo_root.name


def _span_record(repo_key: str, file_path: str, span: list, now: str) -> dict:
    first, last = span[0], span[-1]
    rid = hashlib.sha256(f"{repo_key}:{file_path}:{first.line_no}:{first.commit_sha}".encode()).hexdigest()[:32]
    return {
        "record_id": rid,
        "repo": repo_key,
        "commit_sha": first.commit_sha or "0" * 40,
        "file_path": file_path,
        "line_start": first.line_no,
        "line_end": last.line_no,
        "author_type": first.author_type.value,
        "model": first.model,
        "agent": first.agent.value,
        "content": "\n".join(x.content for x in span),
        "human_edit_ratio": first.human_edit_ratio,
        "reviewed_by": "gitly" if first.reviewed else None,   # summary counts unreviewed as `not reviewed_by`
        "reviewed_at": now if first.reviewed else None,
        "created_at": now,
    }


def build_records(repo_root: Path, repo_key: str, files: list[str]) -> list[dict]:
    """Group each file's per-line provenance into contiguous same-attribution spans → records."""
    now = datetime.now(UTC).isoformat()
    records: list[dict] = []
    for f in files:
        try:
            lines = trace_file(repo_root, f)
        except Exception:
            continue                            # binary / unreadable / untracked — skip
        span: list = []
        key = None
        for ln in lines:
            k = (ln.author_type.value, ln.model, ln.agent.value, ln.commit_sha, ln.reviewed)
            if span and k != key:
                records.append(_span_record(repo_key, f, span, now))
                span = []
            span.append(ln)
            key = k
        if span:
            records.append(_span_record(repo_key, f, span, now))
    return records


def clear_records(api_url: str, repo_key: str) -> int:
    """Delete a key's existing records (so a re-sync replaces rather than accumulates)."""
    url = f"{api_url.rstrip('/')}/trace/records?repo=" + urllib.parse.quote(repo_key, safe="")
    req = urllib.request.Request(url, method="DELETE", headers=_headers())
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read()).get("deleted", 0)


def push_records(api_url: str, records: list[dict], *, batch: int = 500) -> int:
    """POST records to the backend in batches. Returns the total ingested count."""
    total = 0
    base = api_url.rstrip("/")
    for i in range(0, len(records), batch):
        body = json.dumps(records[i:i + batch]).encode()
        req = urllib.request.Request(
            f"{base}/trace/records", data=body, headers=_headers(),
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            total += json.loads(r.read()).get("ingested", 0)
    return total
