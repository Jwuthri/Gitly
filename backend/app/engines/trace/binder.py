"""Bind pending authorship events to the HEAD commit — the post-commit step that turns
capture-time *events* into commit-bound *records* with a real `human_edit_ratio`.

`gitly trace bind` (and the `post-commit` hook `gitly init` installs) call `bind_head`.
Events are consumed via a `.bound` cursor so they're never bound twice."""
from __future__ import annotations

import difflib
import subprocess
from pathlib import Path

from shared.schema.provenance import ProvenanceRecord
from backend.app.engines.trace.recorder import (
    bind_to_commit,
    mark_bound,
    read_bound_ids,
    read_events,
    write_records,
)


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=True
    ).stdout


def _committed_region(proposed: str, committed_file: str) -> str:
    """The slice of the committed file that aligns to the AI's proposed text, so the edit
    ratio compares like-for-like (a span vs the same span), not a span vs the whole file.
    Verbatim proposal → region == proposed → ratio 0; edited → region differs → ratio > 0."""
    blocks = [b for b in difflib.SequenceMatcher(a=proposed, b=committed_file).get_matching_blocks() if b.size]
    if not blocks:
        return ""
    return committed_file[blocks[0].b: blocks[-1].b + blocks[-1].size]


def bind_head(repo_root: Path, *, ledger: str = ".gitly/provenance") -> tuple[str, list[ProvenanceRecord]]:
    """Bind every not-yet-bound event to the current HEAD commit. Returns (sha, records)."""
    head = _git(repo_root, "rev-parse", "HEAD").strip()
    bound = read_bound_ids(repo_root, ledger=ledger)
    pending = [e for e in read_events(repo_root, ledger=ledger) if e.event_id not in bound]
    if not pending:
        return head, []

    committed_by_hash: dict[str, str] = {}
    for e in pending:
        if not e.proposed_text:
            continue
        try:
            file_text = _git(repo_root, "show", f"{head}:{e.file_path}")
        except subprocess.CalledProcessError:
            continue  # file not present in this commit (e.g. deleted / not yet committed)
        committed_by_hash[e.content_hash] = _committed_region(e.proposed_text, file_text)

    records = bind_to_commit(pending, head, committed_by_hash)
    write_records(repo_root, records, ledger=ledger)
    mark_bound(repo_root, [e.event_id for e in pending], ledger=ledger)
    return head, records
