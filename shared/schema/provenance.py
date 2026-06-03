"""Provenance contract — the canonical data model behind `gitly trace`.

The commit-author field credits whoever pressed enter. These records recover the
truth underneath it: which model/agent wrote a span, from which (secret-redacted)
prompt, how much a human changed it afterward, and whether it was reviewed.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class AuthorType(str, Enum):
    human = "human"
    ai = "ai"
    hybrid = "hybrid"   # AI-originated, materially edited by a human


class AgentKind(str, Enum):
    claude_code = "claude_code"
    cursor = "cursor"
    copilot = "copilot"
    windsurf = "windsurf"
    aider = "aider"
    unknown = "unknown"


class ProvenanceEvent(BaseModel):
    """Authorship-time record, written to the local ledger the instant an agent edits
    code — before any commit exists. Keyed by `content_hash` so it can be re-attached
    after a human edits the same span."""
    event_id: str
    repo: str
    file_path: str
    content_hash: str               # sha256 of the AI-proposed span text
    line_start: int
    line_end: int
    author_type: AuthorType = AuthorType.ai
    model: str | None = None        # e.g. "claude-opus-4-8"
    agent: AgentKind = AgentKind.unknown
    agent_version: str | None = None
    session_id: str | None = None
    prompt_ref: str | None = None           # id/hash of the originating prompt
    prompt_redacted: str | None = None      # secret-firewalled prompt text — never raw
    proposed_text: str | None = None        # AI-proposed content (redacted)
    created_at: datetime


class ProvenanceRecord(BaseModel):
    """Commit-bound provenance — the truth `gitly trace` surfaces and the dashboard aggregates."""
    record_id: str
    repo: str
    commit_sha: str
    file_path: str
    line_start: int
    line_end: int
    author_type: AuthorType
    model: str | None = None
    agent: AgentKind = AgentKind.unknown
    session_id: str | None = None
    prompt_ref: str | None = None
    prompt_redacted: str | None = None
    human_edit_ratio: float = 0.0           # 0.0 = untouched AI · 1.0 = fully rewritten by a human
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    bound_at: datetime | None = None


class TraceLine(BaseModel):
    """One line of `gitly trace <file>` output: blame joined with provenance."""
    line_no: int
    content: str
    commit_sha: str | None = None
    author_type: AuthorType = AuthorType.human
    model: str | None = None
    agent: AgentKind = AgentKind.unknown
    human_edit_ratio: float = 0.0
    reviewed: bool = False
    prompt_ref: str | None = None
    inferred: bool = False                  # True when provenance was inferred, not recorded


class TraceSummary(BaseModel):
    """Repo/PR rollup powering the dashboard."""
    repo: str
    total_lines: int = 0
    ai_lines: int = 0
    human_lines: int = 0
    hybrid_lines: int = 0
    unreviewed_ai_lines: int = 0            # the review-prioritization metric
    by_model: dict[str, int] = Field(default_factory=dict)
    by_agent: dict[str, int] = Field(default_factory=dict)
