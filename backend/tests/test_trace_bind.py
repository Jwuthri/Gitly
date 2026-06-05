"""Trace binding: capture events → bind them to a commit → `gitly trace` shows real
edit ratios and hybrid lines (the loop that was previously unwired)."""
from __future__ import annotations

import subprocess
from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from shared.schema.provenance import AgentKind, AuthorType, ProvenanceEvent
from backend.app.cli import app
from backend.app.engines.trace import recorder
from backend.app.engines.trace.binder import _committed_region, bind_head
from backend.app.engines.trace.blame import trace_file

runner = CliRunner()


def _git(cwd, *a) -> str:
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout


@pytest.fixture
def repo(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "checkout", "-q", "-b", "work")
    _git(tmp_path, "config", "user.email", "t@t.co")
    _git(tmp_path, "config", "user.name", "tester")
    return tmp_path


def _event(repo_name, file_path, proposed, *, eid="e1", line_start=1, line_end=None):
    return ProvenanceEvent(
        event_id=eid, repo=repo_name, file_path=file_path,
        content_hash=recorder.content_hash(proposed),
        line_start=line_start, line_end=line_end or (proposed.count("\n") + 1),
        author_type=AuthorType.ai, model="claude-sonnet-4-6", agent=AgentKind.claude_code,
        proposed_text=proposed, created_at=datetime.now(UTC),
    )


def test_committed_region_aligns_a_span_not_the_whole_file():
    proposed = "alpha\nbeta\ngamma\n"
    committed_file = "header\n" + proposed + "footer\n"
    region = _committed_region(proposed, committed_file)
    assert "beta" in region and "header" not in region and "footer" not in region


def test_bind_untouched_ai_is_ratio_zero_and_cursor_prevents_rebind(repo):
    code = "def add(a, b):\n    return a + b\n"
    (repo / "app.py").write_text(code)
    recorder.record_event(repo, _event("r", "app.py", code))
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-qm", "feat: add")

    sha, records = bind_head(repo)
    assert len(records) == 1
    assert records[0].commit_sha == sha
    assert records[0].human_edit_ratio == 0.0           # committed verbatim → no human edit
    assert records[0].author_type == AuthorType.ai

    _, again = bind_head(repo)                            # .bound cursor → no double-binding
    assert again == []
    assert len(recorder.read_records(repo)) == 1


def test_hybrid_flip_when_human_rewrites(repo):
    # bind_to_commit directly, with a committed span very different from the proposal
    ev = _event("r", "app.py", "the AI proposed exactly this line")
    recs = recorder.bind_to_commit([ev], "deadbeefcafe", {ev.content_hash: "a human rewrote it completely"})
    assert recs[0].human_edit_ratio >= 0.5
    assert recs[0].author_type == AuthorType.hybrid


def test_trace_file_prefers_bound_records(repo):
    code = "x = 1\ny = 2\nz = 3\n"
    (repo / "a.py").write_text(code)
    recorder.record_event(repo, _event("r", "a.py", code, line_end=3))
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-qm", "feat: a")
    bind_head(repo)

    lines = trace_file(repo, "a.py")
    ai = [ln for ln in lines if ln.author_type == AuthorType.ai]
    assert ai, "expected AI-attributed lines from the bound record"
    assert ai[0].model == "claude-sonnet-4-6"
    assert all(not ln.inferred for ln in ai)             # recorded, not inferred


def test_trace_untracked_file_is_clean_error(repo, monkeypatch):
    monkeypatch.chdir(repo)
    r = runner.invoke(app, ["trace", "does_not_exist.py"])
    assert r.exit_code == 1
    assert "Can't trace" in r.output            # friendly message, not a traceback


def test_agentkind_normalizes_unknown_values():
    assert AgentKind("my-tool") is AgentKind.unknown   # arbitrary tool name → unknown, never raises
    assert AgentKind("cursor") is AgentKind.cursor
    assert AgentKind("antigravity") is AgentKind.antigravity
    assert AgentKind("kiro") is AgentKind.kiro
    assert AgentKind("continue") is AgentKind.continue_


def test_read_events_tolerates_arbitrary_agent_and_garbage(repo):
    d = repo / ".gitly" / "provenance"
    d.mkdir(parents=True)
    good = ('{"event_id":"e1","repo":"r","file_path":"a.py","content_hash":"h",'
            '"line_start":1,"line_end":1,"agent":"my-tool","created_at":"2026-06-04T00:00:00"}')
    (d / "2026-06-04.jsonl").write_text(good + "\nnot json at all\n")
    events = recorder.read_events(repo)
    assert len(events) == 1                            # garbage line skipped, not a crash
    assert events[0].agent is AgentKind.unknown        # 'my-tool' normalized


def test_review_clears_unreviewed_ai_lines(repo):
    from backend.app.engines.trace.blame import summarize
    code = "x = 1\ny = 2\n"
    (repo / "r.py").write_text(code)
    recorder.record_event(repo, _event("r", "r.py", code, line_end=2))
    _git(repo, "add", "r.py")
    _git(repo, "commit", "-qm", "feat: r")
    bind_head(repo)

    before = summarize(trace_file(repo, "r.py"), repo="r")
    assert before.unreviewed_ai_lines >= 1

    sha = _git(repo, "rev-parse", "HEAD").strip()
    assert recorder.mark_reviewed(repo, [sha], by="me") == 1   # marks it
    assert recorder.mark_reviewed(repo, [sha], by="me") == 0   # idempotent

    after = summarize(trace_file(repo, "r.py"), repo="r")
    assert after.unreviewed_ai_lines == 0
    assert after.ai_lines == before.ai_lines                    # still AI, just reviewed now


def test_sync_build_records_groups_spans(repo):
    from backend.app.engines.trace.sync import build_records, origin_repo_key
    code = "x = 1\ny = 2\n"
    (repo / "s.py").write_text(code)
    recorder.record_event(repo, _event("r", "s.py", code, line_end=2))
    _git(repo, "add", "s.py")
    _git(repo, "commit", "-qm", "feat: s")
    bind_head(repo)

    recs = build_records(repo, "mykey", ["s.py"])
    assert recs, "expected at least one synced record"
    r0 = recs[0]
    assert r0["repo"] == "mykey" and r0["file_path"] == "s.py"
    assert r0["author_type"] == "ai" and r0["content"]      # span carries the code text
    assert r0["record_id"] and r0["created_at"]             # ingest-required fields present
    assert origin_repo_key(repo)                            # falls back to a non-empty key (no remote)


def test_inference_uses_trailers_not_body_mentions(repo):
    from backend.app.engines.trace.blame import _infer_from_commit

    # a commit that merely *mentions* an agent in its subject → NOT attributed to it
    (repo / "x.py").write_text("a = 1\n")
    _git(repo, "add", "x.py")
    _git(repo, "commit", "-qm", "test(copilot): cover the copilot feature")
    sha1 = _git(repo, "rev-parse", "HEAD").strip()
    assert _infer_from_commit(repo, sha1) == (AuthorType.human, AgentKind.unknown)

    # a real Co-Authored-By trailer → inferred AI
    (repo / "y.py").write_text("b = 2\n")
    _git(repo, "add", "y.py")
    _git(repo, "commit", "-qm", "feat: y\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    sha2 = _git(repo, "rev-parse", "HEAD").strip()
    assert _infer_from_commit(repo, sha2) == (AuthorType.ai, AgentKind.claude_code)


def test_bind_skips_files_absent_from_commit(repo):
    # event for a file that never got committed → no committed text, still binds (ratio 0), no crash
    (repo / "real.py").write_text("a = 1\n")
    recorder.record_event(repo, _event("r", "ghost.py", "missing = True\n"))
    _git(repo, "add", "real.py")
    _git(repo, "commit", "-qm", "feat: real")
    sha, records = bind_head(repo)
    assert len(records) == 1 and records[0].file_path == "ghost.py"
    assert records[0].human_edit_ratio == 0.0
