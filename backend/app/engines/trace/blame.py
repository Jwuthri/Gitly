"""`gitly trace <file>` core: git blame joined with recorded provenance.

git blame answers "which commit introduced this line"; provenance answers "who/what
authored that change, from which prompt, and was it reviewed". When no recorded
provenance exists, we *infer* from commit trailers (e.g. `Co-Authored-By: Claude`) and
flag the line as inferred (lower confidence).
"""
from __future__ import annotations

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


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True, text=True, check=True,
    ).stdout


def _blame(repo_root: Path, file_path: str) -> list[tuple[int, str, str]]:
    """Return (line_no, commit_sha, content) using porcelain blame."""
    out = _git(repo_root, "blame", "--line-porcelain", "--", file_path)
    rows: list[tuple[int, str, str]] = []
    sha, lineno = "", 0
    for line in out.splitlines():
        first = line.split(" ", 1)[0].lstrip("^")
        if len(first) == 40 and all(c in "0123456789abcdef" for c in first):
            sha = first
            parts = line.split(" ")
            if len(parts) >= 3 and parts[2].isdigit():
                lineno = int(parts[2])
        elif line.startswith("\t"):
            rows.append((lineno, sha, line[1:]))
    return rows


_TRAILER_KEYS = ("co-authored-by:", "co-developed-by:", "generated-by:", "assisted-by:")


def _infer_from_commit(repo_root: Path, sha: str) -> tuple[AuthorType, AgentKind]:
    """Infer AI authorship ONLY from commit *trailers* (`Co-Authored-By: Claude`) and the
    *author identity* — never a bare mention in the subject/body. (A commit titled
    `test(copilot): …` is *about* Copilot, not written by it — that was a false positive.)"""
    if not sha:
        return AuthorType.human, AgentKind.unknown
    try:
        raw = _git(repo_root, "log", "-1", "--format=%B%x00%an%x00%ae", sha)
    except subprocess.CalledProcessError:
        return AuthorType.human, AgentKind.unknown
    body, _, ident = raw.partition("\x00")
    trailers = " ".join(ln for ln in body.lower().splitlines() if ln.strip().startswith(_TRAILER_KEYS))
    hay = trailers + " " + ident.replace("\x00", " ").lower()   # trailer lines + author name/email
    for needle, agent in _AI_TRAILERS.items():
        if needle in hay:
            return AuthorType.ai, agent
    return AuthorType.human, AgentKind.unknown


def _matches(path_a: str, path_b: str) -> bool:
    return path_a.endswith(path_b) or path_b.endswith(path_a)


def trace_file(repo_root: Path, file_path: str, *, ledger: str = ".gitly/provenance") -> list[TraceLine]:
    """Per-line provenance. Prefers commit-bound *records* (they carry human_edit_ratio +
    review state + hybrid classification), then falls back to raw events, then to inference."""
    records = [r for r in read_records(repo_root, ledger=ledger) if _matches(r.file_path, file_path)]
    events = [e for e in read_events(repo_root, ledger=ledger) if _matches(e.file_path, file_path)]
    reviewed_shas = read_reviewed(repo_root, ledger=ledger)
    out: list[TraceLine] = []
    for line_no, sha, content in _blame(repo_root, file_path):
        seen = sha in reviewed_shas        # human signed off on this commit's AI lines
        # records first: prefer one bound to *this* commit, else any whose span covers the line
        rec = next((r for r in records if r.commit_sha == sha and r.line_start <= line_no <= r.line_end), None) \
            or next((r for r in records if r.line_start <= line_no <= r.line_end), None)
        if rec:
            out.append(TraceLine(
                line_no=line_no, content=content, commit_sha=sha,
                author_type=rec.author_type, model=rec.model, agent=rec.agent,
                human_edit_ratio=rec.human_edit_ratio, reviewed=seen or rec.reviewed_at is not None,
                prompt_ref=rec.prompt_ref,
            ))
            continue
        ev = next((e for e in events if e.line_start <= line_no <= e.line_end), None)
        if ev:
            out.append(TraceLine(
                line_no=line_no, content=content, commit_sha=sha,
                author_type=ev.author_type, model=ev.model, agent=ev.agent,
                reviewed=seen, prompt_ref=ev.prompt_ref,
            ))
            continue
        author, agent = _infer_from_commit(repo_root, sha)
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
        else:
            s.human_lines += 1
        if ln.model:
            s.by_model[ln.model] = s.by_model.get(ln.model, 0) + 1
        s.by_agent[ln.agent.value] = s.by_agent.get(ln.agent.value, 0) + 1
    return s
