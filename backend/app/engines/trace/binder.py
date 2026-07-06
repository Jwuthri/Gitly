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
        ["git", "-C", str(repo_root), *args], capture_output=True, text=True, check=True, timeout=60
    ).stdout


def _rel(repo_root: Path, path: str) -> str:
    """Normalize an event path to repo-relative posix form (capture hooks may record
    absolute paths; `git show HEAD:<path>` and commit file lists need relative ones)."""
    p = Path(path)
    if p.is_absolute():
        try:
            return p.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return p.as_posix()
    return p.as_posix()


def _changed_paths(repo_root: Path, sha: str) -> set[str]:
    """Files touched by `sha` (works for root commits too)."""
    out = _git(repo_root, "show", "--pretty=format:", "--name-only", sha)
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def _committed_region(proposed: str, committed_file: str) -> str:
    """The slice of the committed file that aligns to the AI's proposed text, so the edit
    ratio compares like-for-like (a span vs the same span), not a span vs the whole file.
    Verbatim proposal → region == proposed → ratio 0; edited → region differs → ratio > 0."""
    blocks = [b for b in difflib.SequenceMatcher(a=proposed, b=committed_file).get_matching_blocks() if b.size]
    if not blocks:
        return ""
    return committed_file[blocks[0].b: blocks[-1].b + blocks[-1].size]


def bind_head(repo_root: Path, *, ledger: str = ".gitly/provenance") -> tuple[str, list[ProvenanceRecord]]:
    """Bind not-yet-bound events *whose file HEAD actually touched* to the HEAD commit.
    Events for files outside this commit stay pending, so they bind to the commit that
    really ships them instead of being burned on an unrelated one. Returns (sha, records)."""
    head = _git(repo_root, "rev-parse", "HEAD").strip()
    changed = _changed_paths(repo_root, head)
    bound = read_bound_ids(repo_root, ledger=ledger)
    pending = []
    for e in read_events(repo_root, ledger=ledger):
        if e.event_id in bound:
            continue
        rel = _rel(repo_root, e.file_path)
        if rel not in changed:
            continue                            # not in this commit — stays pending
        pending.append(e.model_copy(update={"file_path": rel}))
    if not pending:
        return head, []

    committed_by_hash: dict[str, str] = {}
    for e in pending:
        if not e.proposed_text:
            continue
        try:
            file_text = _git(repo_root, "show", f"{head}:{e.file_path}")
        except subprocess.CalledProcessError:
            continue  # file not present in this commit (e.g. deleted by it)
        committed_by_hash[e.content_hash] = _committed_region(e.proposed_text, file_text)

    records = bind_to_commit(pending, head, committed_by_hash)
    write_records(repo_root, records, ledger=ledger)
    mark_bound(repo_root, [e.event_id for e in pending], ledger=ledger)
    return head, records


def _needle(proposed: str | None) -> str | None:
    """A distinctive single line of the proposal for `git log -S` (pickaxe)."""
    for ln in (proposed or "").splitlines():
        if len(ln.strip()) >= 8:
            return ln
    return None


def backfill(repo_root: Path, *, ledger: str = ".gitly/provenance") -> list[tuple[str, int]]:
    """Bind stranded pending events (their commit happened without the post-commit hook)
    to the commit that actually introduced their content, found via pickaxe search.
    Events whose content never landed in history stay pending. Returns [(sha, bound), …]."""
    bound = read_bound_ids(repo_root, ledger=ledger)
    by_sha: dict[str, list] = {}
    for e in read_events(repo_root, ledger=ledger):
        if e.event_id in bound:
            continue
        rel = _rel(repo_root, e.file_path)
        needle = _needle(e.proposed_text)
        if not needle:
            continue
        try:
            sha = _git(repo_root, "log", "-n", "1", "--format=%H", "-S", needle, "--", rel).strip()
        except subprocess.CalledProcessError:
            continue
        if sha:
            by_sha.setdefault(sha, []).append(e.model_copy(update={"file_path": rel}))

    out: list[tuple[str, int]] = []
    for sha, evs in by_sha.items():
        committed_by_hash: dict[str, str] = {}
        for e in evs:
            if not e.proposed_text:
                continue
            try:
                file_text = _git(repo_root, "show", f"{sha}:{e.file_path}")
            except subprocess.CalledProcessError:
                continue
            committed_by_hash[e.content_hash] = _committed_region(e.proposed_text, file_text)
        records = bind_to_commit(evs, sha, committed_by_hash)
        write_records(repo_root, records, ledger=ledger)
        mark_bound(repo_root, [e.event_id for e in evs], ledger=ledger)
        out.append((sha, len(records)))
    return out
