"""Provenance recorder — write authorship events to the local ledger and bind them to commits.

Capture (authorship time): `record_event()` appends to `.gitly/provenance/<date>.jsonl`,
redacting the prompt first so secrets never hit disk.
Bind (commit time): `bind_to_commit()` attaches pending events to a commit SHA and computes
`human_edit_ratio` (how much a human changed the AI's proposal before committing).
"""
from __future__ import annotations

import difflib
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from shared.schema.provenance import ProvenanceEvent, ProvenanceRecord
from backend.app.security.secret_firewall import redact


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ledger_dir(repo_root: Path, ledger: str) -> Path:
    d = repo_root / ledger
    d.mkdir(parents=True, exist_ok=True)
    return d


def record_event(repo_root: Path, event: ProvenanceEvent, *, ledger: str = ".gitly/provenance") -> None:
    """Append one authorship event to the local ledger, redacting prompt + proposed text."""
    safe = event.model_copy(update={
        "prompt_redacted": redact(event.prompt_redacted) if event.prompt_redacted else None,
        "proposed_text": redact(event.proposed_text) if event.proposed_text else None,
    })
    day = safe.created_at.strftime("%Y-%m-%d")
    path = _ledger_dir(repo_root, ledger) / f"{day}.jsonl"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(safe.model_dump_json() + "\n")


def read_events(repo_root: Path, *, ledger: str = ".gitly/provenance") -> list[ProvenanceEvent]:
    d = repo_root / ledger
    if not d.exists():
        return []
    events: list[ProvenanceEvent] = []
    for f in sorted(d.glob("*.jsonl")):       # top-level only — bound records live in records/
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(ProvenanceEvent.model_validate_json(line))
            except Exception:
                continue                       # skip a malformed/old-schema line, don't crash trace
    return events


# ---- bound records: the commit-bound truth, written by the post-commit bind step ----

def write_records(repo_root: Path, records: list[ProvenanceRecord], *, ledger: str = ".gitly/provenance") -> None:
    """Append commit-bound records to `<ledger>/records/<date>.jsonl`, re-redacting the prompt."""
    if not records:
        return
    d = _ledger_dir(repo_root, f"{ledger}/records")
    for r in records:
        safe = r.model_copy(update={"prompt_redacted": redact(r.prompt_redacted) if r.prompt_redacted else None})
        day = (safe.bound_at or safe.created_at).strftime("%Y-%m-%d")
        with (d / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(safe.model_dump_json() + "\n")


def read_records(repo_root: Path, *, ledger: str = ".gitly/provenance") -> list[ProvenanceRecord]:
    d = repo_root / ledger / "records"
    if not d.exists():
        return []
    records: list[ProvenanceRecord] = []
    for f in sorted(d.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                records.append(ProvenanceRecord.model_validate_json(line))
            except Exception:
                continue                       # skip a malformed line, don't crash trace
    return records


def read_bound_ids(repo_root: Path, *, ledger: str = ".gitly/provenance") -> set[str]:
    """Event ids already bound to a commit (so we never double-bind)."""
    f = repo_root / ledger / ".bound"
    if not f.exists():
        return set()
    return {ln.strip() for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()}


def mark_bound(repo_root: Path, event_ids: list[str], *, ledger: str = ".gitly/provenance") -> None:
    if not event_ids:
        return
    f = _ledger_dir(repo_root, ledger) / ".bound"
    with f.open("a", encoding="utf-8") as fh:
        for eid in event_ids:
            fh.write(eid + "\n")


# ---- review: mark AI-authored commits as human-reviewed (local, blame-sha based) ----

def read_reviewed(repo_root: Path, *, ledger: str = ".gitly/provenance") -> set[str]:
    """Commit SHAs whose AI lines a human has signed off on."""
    f = repo_root / ledger / "reviewed.jsonl"
    if not f.exists():
        return set()
    out: set[str] = set()
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.add(json.loads(line)["commit_sha"])
        except Exception:
            continue
    return out


def mark_reviewed(repo_root: Path, commit_shas: list[str], *, by: str = "", ledger: str = ".gitly/provenance") -> int:
    """Record that `commit_shas` were reviewed. Idempotent — already-reviewed shas are skipped.
    Returns the count newly marked."""
    existing = read_reviewed(repo_root, ledger=ledger)
    fresh = [s for s in dict.fromkeys(commit_shas) if s and s not in existing]
    if not fresh:
        return 0
    f = _ledger_dir(repo_root, ledger) / "reviewed.jsonl"
    now = datetime.now(UTC).isoformat()
    with f.open("a", encoding="utf-8") as fh:
        for s in fresh:
            fh.write(json.dumps({"commit_sha": s, "reviewed_by": by, "reviewed_at": now}) + "\n")
    return len(fresh)


def human_edit_ratio(proposed: str, committed: str) -> float:
    """Fraction of the AI-proposed span a human changed before committing (0..1)."""
    if not proposed:
        return 0.0
    return round(1.0 - difflib.SequenceMatcher(a=proposed, b=committed).ratio(), 3)


def bind_to_commit(
    events: list[ProvenanceEvent],
    commit_sha: str,
    committed_text_by_hash: dict[str, str] | None = None,
) -> list[ProvenanceRecord]:
    """Turn pending authorship events into commit-bound records. If the committed text for
    a span is provided, classify human-edited spans as `hybrid` and set the edit ratio."""
    committed_text_by_hash = committed_text_by_hash or {}
    records: list[ProvenanceRecord] = []
    now = datetime.now(UTC)
    for e in events:
        committed = committed_text_by_hash.get(e.content_hash)
        ratio = human_edit_ratio(e.proposed_text or "", committed) if committed else 0.0
        author = e.author_type
        if ratio >= 0.5:
            from shared.schema.provenance import AuthorType
            author = AuthorType.hybrid
        records.append(ProvenanceRecord(
            record_id=content_hash(f"{commit_sha}:{e.file_path}:{e.line_start}:{e.event_id}")[:32],
            repo=e.repo, commit_sha=commit_sha, file_path=e.file_path,
            line_start=e.line_start, line_end=e.line_end, author_type=author,
            model=e.model, agent=e.agent, session_id=e.session_id,
            prompt_ref=e.prompt_ref, prompt_redacted=e.prompt_redacted,
            content=committed, human_edit_ratio=ratio, created_at=e.created_at, bound_at=now,
        ))
    return records
