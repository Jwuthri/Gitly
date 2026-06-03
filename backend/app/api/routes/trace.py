"""Provenance API — opt-in sync of commit-bound authorship records + dashboard rollups."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import ProvenanceRecordORM
from backend.app.db.session import get_db
from backend.app.security.secret_firewall import redact
from shared.schema.provenance import ProvenanceRecord, TraceSummary

router = APIRouter(prefix="/trace", tags=["trace"])


@router.post("/records")
def ingest_records(records: list[ProvenanceRecord], db: Session = Depends(get_db)):
    """Sync commit-bound provenance from a developer's machine (opt-in). Prompts are
    re-redacted defensively on ingest, so a raw secret can never land in the DB."""
    for r in records:
        db.merge(ProvenanceRecordORM(
            record_id=r.record_id, repo=r.repo, commit_sha=r.commit_sha,
            file_path=r.file_path, line_start=r.line_start, line_end=r.line_end,
            author_type=r.author_type.value, model=r.model, agent=r.agent.value,
            session_id=r.session_id, prompt_ref=r.prompt_ref,
            prompt_redacted=redact(r.prompt_redacted) if r.prompt_redacted else None,
            human_edit_ratio=r.human_edit_ratio, reviewed_by=r.reviewed_by,
            reviewed_at=r.reviewed_at, created_at=r.created_at, bound_at=r.bound_at,
        ))
    db.commit()
    return {"ingested": len(records)}


@router.get("/summary")
def repo_summary(repo: str, db: Session = Depends(get_db)) -> TraceSummary:
    rows = db.execute(
        select(ProvenanceRecordORM).where(ProvenanceRecordORM.repo == repo)
    ).scalars().all()
    s = TraceSummary(repo=repo)
    for r in rows:
        span = max(1, r.line_end - r.line_start + 1)
        s.total_lines += span
        if r.author_type == "ai":
            s.ai_lines += span
            if not r.reviewed_by:
                s.unreviewed_ai_lines += span
        elif r.author_type == "hybrid":
            s.hybrid_lines += span
        else:
            s.human_lines += span
        if r.model:
            s.by_model[r.model] = s.by_model.get(r.model, 0) + span
        s.by_agent[r.agent] = s.by_agent.get(r.agent, 0) + span
    return s


@router.get("/records")
def list_records(repo: str, db: Session = Depends(get_db)):
    rows = db.execute(
        select(ProvenanceRecordORM).where(ProvenanceRecordORM.repo == repo).limit(500)
    ).scalars().all()
    return [
        {
            "file_path": r.file_path,
            "commit_sha": r.commit_sha[:8],
            "author_type": r.author_type,
            "model": r.model,
            "agent": r.agent,
            "human_edit_ratio": r.human_edit_ratio,
            "reviewed": bool(r.reviewed_by),
            "lines": f"{r.line_start}-{r.line_end}",
        }
        for r in rows
    ]
