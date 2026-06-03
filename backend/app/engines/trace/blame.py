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
from backend.app.engines.trace.recorder import read_events

_AI_TRAILERS = {
    "claude": AgentKind.claude_code,
    "cursor": AgentKind.cursor,
    "copilot": AgentKind.copilot,
    "aider": AgentKind.aider,
    "windsurf": AgentKind.windsurf,
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


def _infer_from_commit(repo_root: Path, sha: str) -> tuple[AuthorType, AgentKind]:
    if not sha:
        return AuthorType.human, AgentKind.unknown
    try:
        msg = _git(repo_root, "log", "-1", "--format=%B%n%an%n%ae", sha).lower()
    except subprocess.CalledProcessError:
        return AuthorType.human, AgentKind.unknown
    for needle, agent in _AI_TRAILERS.items():
        if needle in msg:
            return AuthorType.ai, agent
    return AuthorType.human, AgentKind.unknown


def trace_file(repo_root: Path, file_path: str, *, ledger: str = ".gitly/provenance") -> list[TraceLine]:
    events = read_events(repo_root, ledger=ledger)
    by_file = [e for e in events if e.file_path.endswith(file_path) or file_path.endswith(e.file_path)]
    out: list[TraceLine] = []
    for line_no, sha, content in _blame(repo_root, file_path):
        match = next((e for e in by_file if e.line_start <= line_no <= e.line_end), None)
        if match:
            out.append(TraceLine(
                line_no=line_no, content=content, commit_sha=sha,
                author_type=match.author_type, model=match.model, agent=match.agent,
                prompt_ref=match.prompt_ref,
            ))
        else:
            author, agent = _infer_from_commit(repo_root, sha)
            out.append(TraceLine(
                line_no=line_no, content=content, commit_sha=sha,
                author_type=author, agent=agent, inferred=author != AuthorType.human,
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
