"""Attribution must stay truthful as the repo evolves: bound records may only speak for
the commit they were bound to, events only for not-yet-committed lines, and inference
must not fire on lookalike words. These are the "who really wrote this line" guarantees."""
from __future__ import annotations

import subprocess
from datetime import UTC, datetime

import pytest

from shared.schema.provenance import AgentKind, AuthorType, ProvenanceEvent
from backend.app.engines.trace import recorder
from backend.app.engines.trace.binder import bind_head
from backend.app.engines.trace.blame import _infer_from_commit, _matches, trace_file


def _git(cwd, *a) -> str:
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "checkout", "-q", "-b", "work")
    _git(tmp_path, "config", "user.email", "t@t.co")
    _git(tmp_path, "config", "user.name", "tester")
    return tmp_path


def _event(file_path, proposed, *, eid="e1", line_start=1, line_end=None):
    return ProvenanceEvent(
        event_id=eid, repo="r", file_path=file_path,
        content_hash=recorder.content_hash(proposed),
        line_start=line_start, line_end=line_end or (line_start + proposed.count("\n")),
        author_type=AuthorType.ai, model="claude-sonnet-4-6", agent=AgentKind.claude_code,
        proposed_text=proposed, created_at=datetime.now(UTC),
    )


def _commit_ai_block(repo, name="a.py", code="x = 1\ny = 2\nz = 3\n"):
    (repo / name).write_text(code)
    recorder.record_event(repo, _event(name, code))
    _git(repo, "add", name)
    _git(repo, "commit", "-qm", f"feat: {name}")
    bind_head(repo)


def test_human_rewrite_is_not_claimed_by_the_stale_ai_record(repo):
    _commit_ai_block(repo)                                   # AI wrote lines 1-3, bound
    text = (repo / "a.py").read_text().splitlines()
    text[1] = "y = 'a human rewrote this line'"              # human rewrites line 2
    (repo / "a.py").write_text("\n".join(text) + "\n")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-qm", "fix: correct y")            # no event, no trailer → human

    lines = trace_file(repo, "a.py")
    assert lines[0].author_type == AuthorType.ai             # untouched AI lines stay AI
    assert lines[2].author_type == AuthorType.ai
    assert lines[1].author_type == AuthorType.human          # the rewrite is human — not the record's

def test_ai_attribution_survives_insertions_above_the_span(repo):
    _commit_ai_block(repo)                                   # AI block at lines 1-3
    body = (repo / "a.py").read_text()
    (repo / "a.py").write_text("# header\n# by hand\n" + body)   # human prepends 2 lines
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-qm", "docs: header")

    lines = trace_file(repo, "a.py")
    assert [ln.author_type for ln in lines[:2]] == [AuthorType.human] * 2
    # the AI block shifted to lines 3-5 but blame's orig line numbers still land in the record
    assert [ln.author_type for ln in lines[2:]] == [AuthorType.ai] * 3


def test_events_only_claim_uncommitted_lines(repo):
    (repo / "w.py").write_text("a = 1\nb = 2\n")
    _git(repo, "add", "w.py")
    _git(repo, "commit", "-qm", "feat: human start")

    new = "c = 3\nd = 4\n"
    (repo / "w.py").write_text("a = 1\nb = 2\n" + new)       # AI appends, not committed yet
    recorder.record_event(repo, _event("w.py", new, line_start=3))

    lines = trace_file(repo, "w.py")
    assert [ln.author_type for ln in lines] == [AuthorType.human, AuthorType.human, AuthorType.ai, AuthorType.ai]
    assert lines[2].commit_sha is None                       # uncommitted — no sha to show
    # committed human lines must never be re-claimed by the event span
    assert lines[0].commit_sha is not None


def test_matches_requires_a_path_boundary():
    assert _matches("foo/bar.py", "bar.py")
    assert _matches("/abs/repo/foo/bar.py", "foo/bar.py")
    assert _matches("bar.py", "bar.py")
    assert not _matches("foo/bar.py", "ar.py")               # suffix without a boundary
    assert not _matches("foobar.py", "bar.py")


def test_reviewed_by_trailer_counts_as_human_review(repo):
    # zero-command review: a Reviewed-by/Acked-by trailer on the commit clears the AI lines
    from backend.app.engines.trace.blame import summarize
    (repo / "r.py").write_text("a = 1\n")
    _git(repo, "add", "r.py")
    _git(repo, "commit", "-qm",
         "feat: r\n\nCo-Authored-By: Claude <noreply@anthropic.com>\nReviewed-by: Alice <alice@corp.com>")

    lines = trace_file(repo, "r.py")
    assert lines[0].author_type == AuthorType.ai and lines[0].reviewed
    assert summarize(lines, repo="r").unreviewed_ai_lines == 0

    # same AI trailer WITHOUT a review trailer stays unreviewed
    (repo / "u.py").write_text("b = 2\n")
    _git(repo, "add", "u.py")
    _git(repo, "commit", "-qm", "feat: u\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    assert summarize(trace_file(repo, "u.py"), repo="r").unreviewed_ai_lines == 1


def test_parse_gh_pr_list_extracts_approved_prs_and_humans():
    import json as _json
    from backend.app.cli import _parse_gh_pr_list
    payload = _json.dumps([
        {"number": 1, "reviewDecision": "APPROVED",
         "latestReviews": [
             {"state": "APPROVED", "author": {"login": "alice"}},
             {"state": "APPROVED", "author": {"login": "dependabot[bot]"}},   # bots don't count
             {"state": "COMMENTED", "author": {"login": "carol"}},
         ]},
        {"number": 2, "reviewDecision": "REVIEW_REQUIRED", "latestReviews": []},   # skipped
        {"number": 3, "reviewDecision": "APPROVED", "latestReviews": []},
    ])
    numbers, approvers = _parse_gh_pr_list(payload)
    assert numbers == [1, 3]
    assert approvers == {"alice"}


def test_inference_needles_match_words_not_substrings(repo):
    (repo / "p.py").write_text("a = 1\n")
    _git(repo, "add", "p.py")
    _git(repo, "commit", "-qm", "feat: p\n\nCo-Authored-By: Precursor <bot@precursor.dev>")
    sha = _git(repo, "rev-parse", "HEAD").strip()
    assert _infer_from_commit(repo, sha) == (AuthorType.human, AgentKind.unknown)   # not 'cursor'

    (repo / "q.py").write_text("b = 2\n")
    _git(repo, "add", "q.py")
    _git(repo, "commit", "-qm", "feat: q\n\nCo-Authored-By: Cursor <agent@cursor.com>")
    sha2 = _git(repo, "rev-parse", "HEAD").strip()
    assert _infer_from_commit(repo, sha2) == (AuthorType.ai, AgentKind.cursor)
