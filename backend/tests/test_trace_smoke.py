from __future__ import annotations

from datetime import UTC, datetime

from backend.app.engines.trace.blame import summarize
from backend.app.security.secret_firewall import redact, scan
from shared.schema.provenance import AgentKind, AuthorType, ProvenanceEvent, TraceLine


def test_secret_firewall_detects_and_redacts():
    text = 'api_key = "AKIA1234567890ABCDEF"\nopenai = "sk-abcdefghijklmnopqrstuvwxyz0123"'
    findings = scan(text)
    assert findings, "should detect at least one secret"
    red = redact(text)
    assert "AKIA1234567890ABCDEF" not in red
    assert "‹redacted:" in red


def test_provenance_event_roundtrips():
    e = ProvenanceEvent(
        event_id="e1", repo="demo", file_path="a.py", content_hash="x",
        line_start=1, line_end=3, model="claude-opus-4-8", agent=AgentKind.claude_code,
        created_at=datetime.now(UTC),
    )
    again = ProvenanceEvent.model_validate_json(e.model_dump_json())
    assert again.model == "claude-opus-4-8"
    assert again.author_type == AuthorType.ai


def test_summarize_counts_unreviewed_ai():
    lines = [
        TraceLine(line_no=1, content="x", author_type=AuthorType.ai, model="claude-opus-4-8"),
        TraceLine(line_no=2, content="y", author_type=AuthorType.human),
        TraceLine(line_no=3, content="z", author_type=AuthorType.ai, reviewed=True, model="claude-opus-4-8"),
    ]
    s = summarize(lines, repo="demo")
    assert s.ai_lines == 2
    assert s.unreviewed_ai_lines == 1
    assert s.by_model["claude-opus-4-8"] == 2
