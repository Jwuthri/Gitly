"""`gitly trace <file>` core: git blame joined with recorded provenance.

git blame answers "which commit introduced this line"; provenance answers "who/what
authored that change, from which prompt, and was it reviewed". When no recorded
provenance exists, we *infer* from commit trailers (e.g. `Co-Authored-By: Claude`) and
flag the line as inferred (lower confidence).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from shared.schema.provenance import AgentKind, AuthorType, TraceLine, TraceSummary
from backend.app.engines.trace.recorder import read_events, read_records, read_reviewed

_AI_TRAILERS = {
    # more-specific needles first — first match wins
    "openai codex": AgentKind.openai_codex,
    "sourcegraph cody": AgentKind.cody,
    "kiro": AgentKind.kiro,
    "jetbrains ai": AgentKind.jetbrains_ai,
    "claude": AgentKind.claude_code,
    "cursor": AgentKind.cursor,
    "copilot": AgentKind.copilot,
    "aider": AgentKind.aider,
    "windsurf": AgentKind.windsurf,
    "antigravity": AgentKind.antigravity,
    "lovable": AgentKind.lovable,
    "gemini": AgentKind.gemini,
    "devin": AgentKind.devin,
    "replit": AgentKind.replit,
    "tabnine": AgentKind.tabnine,
}


_NULL_SHA = "0" * 40  # blame's sha for lines not committed yet


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True, text=True, check=True, timeout=60,
    ).stdout


def _blame(repo_root: Path, file_path: str) -> list[tuple[int, int, str, str]]:
    """Return (final_line_no, orig_line_no, commit_sha, content) using porcelain blame.
    `orig_line_no` is the line's number *in the commit that introduced it* — the coordinate
    bound records are keyed by, so attribution survives later insertions above the span."""
    out = _git(repo_root, "blame", "--line-porcelain", "--", file_path)
    rows: list[tuple[int, int, str, str]] = []
    sha, orig, final = "", 0, 0
    for line in out.splitlines():
        first = line.split(" ", 1)[0].lstrip("^")
        if len(first) == 40 and all(c in "0123456789abcdef" for c in first):
            sha = first
            parts = line.split(" ")
            if len(parts) >= 3 and parts[1].isdigit() and parts[2].isdigit():
                orig, final = int(parts[1]), int(parts[2])
        elif line.startswith("\t"):
            rows.append((final, orig, sha, line[1:]))
    return rows


_TRAILER_KEYS = ("co-authored-by:", "co-developed-by:", "generated-by:", "assisted-by:")
_REVIEW_TRAILERS = ("reviewed-by:", "acked-by:")   # kernel-style human sign-off, free review signal


def _commit_meta(repo_root: Path, sha: str) -> tuple[AuthorType, AgentKind, bool]:
    """(author_type, agent, human_review_trailer) for a commit — one `git log` per sha.

    AI authorship is inferred ONLY from commit *trailers* (`Co-Authored-By: Claude`) and the
    *author identity* — never a bare mention in the subject/body. (A commit titled
    `test(copilot): …` is *about* Copilot, not written by it — that was a false positive.)
    Needles match at word boundaries, so 'Precursor' is not 'cursor'. Known limit: a human
    literally named after an agent (e.g. Devin) still matches — recorded provenance wins
    over inference whenever it exists.

    A `Reviewed-by:`/`Acked-by:` trailer counts as human review, so teams already using
    those conventions get review status with zero extra commands."""
    if not sha or sha == _NULL_SHA:
        return AuthorType.human, AgentKind.unknown, False
    try:
        raw = _git(repo_root, "log", "-1", "--format=%B%x00%an%x00%ae", sha)
    except subprocess.CalledProcessError:
        return AuthorType.human, AgentKind.unknown, False
    body, _, ident = raw.partition("\x00")
    body_lines = [ln.strip() for ln in body.lower().splitlines()]
    reviewed = any(ln.startswith(_REVIEW_TRAILERS) for ln in body_lines)
    trailers = " ".join(ln for ln in body_lines if ln.startswith(_TRAILER_KEYS))
    hay = trailers + " " + ident.replace("\x00", " ").lower()   # trailer lines + author name/email
    for needle, agent in _AI_TRAILERS.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", hay):
            return AuthorType.ai, agent, reviewed
    return AuthorType.human, AgentKind.unknown, reviewed


def _infer_from_commit(repo_root: Path, sha: str) -> tuple[AuthorType, AgentKind]:
    """Back-compat shim over `_commit_meta` (authorship only)."""
    author, agent, _ = _commit_meta(repo_root, sha)
    return author, agent


def _matches(path_a: str, path_b: str) -> bool:
    """Same file? Tolerates one side being absolute or repo-relative, but only matches at a
    path-segment boundary — 'foo/bar.py' must never match 'ar.py'."""
    a = path_a.replace("\\", "/").rstrip("/")
    b = path_b.replace("\\", "/").rstrip("/")
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def trace_file(repo_root: Path, file_path: str, *, ledger: str = ".gitly/provenance") -> list[TraceLine]:
    """Per-line provenance. A bound *record* is trusted only for the commit it was bound to,
    at the line's position in that commit (blame's orig line number) — so a record can never
    claim a line a human later rewrote, and attribution survives insertions above the span.
    Raw *events* (pre-commit captures) only ever explain not-yet-committed lines; everything
    else falls back to commit-trailer inference (flagged `inferred`, cached per sha)."""
    records = [r for r in read_records(repo_root, ledger=ledger) if _matches(r.file_path, file_path)]
    events = [e for e in read_events(repo_root, ledger=ledger) if _matches(e.file_path, file_path)]
    reviewed_shas = read_reviewed(repo_root, ledger=ledger)
    meta_cache: dict[str, tuple[AuthorType, AgentKind, bool]] = {}

    def meta(sha: str) -> tuple[AuthorType, AgentKind, bool]:
        if sha not in meta_cache:
            meta_cache[sha] = _commit_meta(repo_root, sha)
        return meta_cache[sha]

    out: list[TraceLine] = []
    for line_no, orig_no, sha, content in _blame(repo_root, file_path):
        uncommitted = not sha or sha == _NULL_SHA
        # review signal from ANY source: explicit `gitly review` / synced GitHub approvals
        # (reviewed.jsonl) or a Reviewed-by/Acked-by trailer on the commit itself
        seen = not uncommitted and (sha in reviewed_shas or meta(sha)[2])
        rec = None
        if not uncommitted:
            rec = next((r for r in records
                        if r.commit_sha == sha and r.line_start <= orig_no <= r.line_end), None)
        if rec:
            out.append(TraceLine(
                line_no=line_no, content=content, commit_sha=sha,
                author_type=rec.author_type, model=rec.model, agent=rec.agent,
                human_edit_ratio=rec.human_edit_ratio, reviewed=seen or rec.reviewed_at is not None,
                prompt_ref=rec.prompt_ref,
            ))
            continue
        if uncommitted:
            ev = next((e for e in events if e.line_start <= line_no <= e.line_end), None)
            if ev:
                out.append(TraceLine(
                    line_no=line_no, content=content, commit_sha=None,
                    author_type=ev.author_type, model=ev.model, agent=ev.agent,
                    reviewed=False, prompt_ref=ev.prompt_ref,
                ))
            else:   # uncommitted and unrecorded → a human is typing
                out.append(TraceLine(line_no=line_no, content=content, commit_sha=None))
            continue
        author, agent, _ = meta(sha)
        out.append(TraceLine(
            line_no=line_no, content=content, commit_sha=sha,
            author_type=author, agent=agent, reviewed=seen, inferred=author != AuthorType.human,
        ))
    return out


def summarize(lines: list[TraceLine], repo: str) -> TraceSummary:
    s = TraceSummary(repo=repo, total_lines=len(lines))
    for ln in lines:
        if ln.author_type == AuthorType.ai:
            s.ai_lines += 1
            if not ln.reviewed:
                s.unreviewed_ai_lines += 1
        elif ln.author_type == AuthorType.hybrid:
            s.hybrid_lines += 1
            if not ln.reviewed:                 # hybrid is AI-originated — it's review debt too
                s.unreviewed_ai_lines += 1
        else:
            s.human_lines += 1
        if ln.model:
            s.by_model[ln.model] = s.by_model.get(ln.model, 0) + 1
        if ln.author_type != AuthorType.human:   # by_agent is an AI rollup — humans aren't an "agent"
            s.by_agent[ln.agent.value] = s.by_agent.get(ln.agent.value, 0) + 1
    return s
