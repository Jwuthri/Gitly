"""Provenance recorder — write authorship events to the local ledger and bind them to commits.

Capture (authorship time): `record_event()` appends to `.gitly/provenance/<date>.jsonl`,
redacting the prompt first so secrets never hit disk.
Bind (commit time): `bind_to_commit()` attaches pending events to a commit SHA and computes
`human_edit_ratio` (how much a human changed the AI's proposal before committing).
"""
from __future__ import annotations

import difflib
import hashlib
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
    for f in sorted(d.glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(ProvenanceEvent.model_validate_json(line))
    return events


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
            human_edit_ratio=ratio, created_at=e.created_at, bound_at=now,
        ))
    return records
