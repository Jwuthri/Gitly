from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


def _now() -> datetime:
    return datetime.now(UTC)


class ProvenanceRecordORM(Base):
    """Commit-bound AI-authorship provenance. Mirrors shared.schema.provenance.ProvenanceRecord."""

    __tablename__ = "provenance_records"

    record_id: Mapped[str] = mapped_column(String, primary_key=True)
    repo: Mapped[str] = mapped_column(String, index=True)
    commit_sha: Mapped[str] = mapped_column(String, index=True)
    file_path: Mapped[str] = mapped_column(String, index=True)
    line_start: Mapped[int] = mapped_column(Integer)
    line_end: Mapped[int] = mapped_column(Integer)
    author_type: Mapped[str] = mapped_column(String, default="ai")
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    agent: Mapped[str] = mapped_column(String, default="unknown")
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_edit_ratio: Mapped[float] = mapped_column(Float, default=0.0)
    reviewed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    bound_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class JobORM(Base):
    """Async job (shrink / lens / trace-sync) processed by a Celery worker."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)            # shrink | lens | trace_sync
    status: Mapped[str] = mapped_column(String, default="pending")
    repo: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
