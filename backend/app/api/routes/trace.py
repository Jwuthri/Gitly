"""Provenance API — opt-in sync of authorship records, rollups, file tree, and per-line blame."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.db.models import ProvenanceRecordORM
from backend.app.db.session import get_db
from backend.app.security.secret_firewall import redact
from shared.schema.provenance import ProvenanceRecord, TraceSummary

router = APIRouter(prefix="/trace", tags=["trace"])

MAX_INGEST_RECORDS = 5000       # per request — sync batches at 500, so 10× headroom


def require_write_key(authorization: str | None = Header(None)) -> None:
    """Guard mutating routes. With GITLY_API_KEY unset (local dev) this is a no-op;
    set it anywhere the backend is reachable by more than your own machine."""
    key = get_settings().gitly_api_key
    if not key:
        return
    if authorization != f"Bearer {key}":
        raise HTTPException(status_code=401, detail="Set 'Authorization: Bearer <GITLY_API_KEY>'.")


@router.post("/records", dependencies=[Depends(require_write_key)])
def ingest_records(records: list[ProvenanceRecord], db: Session = Depends(get_db)):
    """Sync authorship records from a developer's machine (opt-in). Prompts are re-redacted
    defensively on ingest, so a raw secret can never land in the DB."""
    if len(records) > MAX_INGEST_RECORDS:
        raise HTTPException(status_code=413, detail=f"Max {MAX_INGEST_RECORDS} records per request — batch your sync.")
    for r in records:
        db.merge(ProvenanceRecordORM(
            record_id=r.record_id, repo=r.repo, commit_sha=r.commit_sha,
            file_path=r.file_path, line_start=r.line_start, line_end=r.line_end,
            author_type=r.author_type.value, model=r.model, agent=r.agent.value,
            session_id=r.session_id, prompt_ref=r.prompt_ref,
            prompt_redacted=redact(r.prompt_redacted) if r.prompt_redacted else None,
            content=r.content,
            human_edit_ratio=r.human_edit_ratio, reviewed_by=r.reviewed_by,
            reviewed_at=r.reviewed_at, created_at=r.created_at, bound_at=r.bound_at,
        ))
    db.commit()
    return {"ingested": len(records)}


@router.delete("/records", dependencies=[Depends(require_write_key)])
def delete_records(repo: str, db: Session = Depends(get_db)):
    """Clear all records for a repo key (used by `gitly sync --reset` to avoid pile-up)."""
    n = db.execute(delete(ProvenanceRecordORM).where(ProvenanceRecordORM.repo == repo)).rowcount
    db.commit()
    return {"deleted": n}


def _records_for(db: Session, repo: str):
    return db.execute(
        select(ProvenanceRecordORM).where(ProvenanceRecordORM.repo == repo)
    ).scalars().all()


@router.get("/summary")
def repo_summary(repo: str, db: Session = Depends(get_db)) -> TraceSummary:
    s = TraceSummary(repo=repo)
    for r in _records_for(db, repo):
        span = max(1, r.line_end - r.line_start + 1)
        s.total_lines += span
        if r.author_type == "ai":
            s.ai_lines += span
            if not r.reviewed_by:
                s.unreviewed_ai_lines += span
        elif r.author_type == "hybrid":
            s.hybrid_lines += span
            if not r.reviewed_by:               # hybrid is AI-originated — review debt too
                s.unreviewed_ai_lines += span
        else:
            s.human_lines += span
        if r.model:
            s.by_model[r.model] = s.by_model.get(r.model, 0) + span
        if r.author_type != "human":             # by_agent is an AI rollup — humans aren't an "agent"
            s.by_agent[r.agent] = s.by_agent.get(r.agent, 0) + span
    return s


@router.get("/tree")
def file_tree(repo: str, db: Session = Depends(get_db)):
    """Per-file authorship rollup for the file-tree sidebar."""
    by_file: dict[str, dict] = {}
    for r in _records_for(db, repo):
        span = max(1, r.line_end - r.line_start + 1)
        f = by_file.setdefault(r.file_path, {"path": r.file_path, "lines": 0, "ai_lines": 0, "unreviewed": 0})
        f["lines"] = max(f["lines"], r.line_end)
        if r.author_type in ("ai", "hybrid"):
            f["ai_lines"] += span
            if not r.reviewed_by:
                f["unreviewed"] += span
    return {"repo": repo, "files": sorted(by_file.values(), key=lambda x: x["path"])}


@router.get("/file")
def file_blame(repo: str, path: str, db: Session = Depends(get_db)):
    """Per-line blame for one file: each line tagged with who authored it. Reconstructed
    from the file's stored record spans (the web equivalent of `gitly trace <file>`)."""
    rows = sorted(
        [r for r in _records_for(db, repo) if r.file_path == path],
        key=lambda r: r.line_start,
    )
    lines: list[dict] = []
    for r in rows:
        body = (r.content or "").split("\n") if r.content else [""] * (r.line_end - r.line_start + 1)
        for i, text in enumerate(body):
            ln = r.line_start + i
            if ln > r.line_end:
                break
            lines.append({
                "line_no": ln,
                "content": text,
                "author_type": r.author_type,
                "model": r.model,
                "agent": r.agent,
                "reviewed": bool(r.reviewed_by),
                "human_edit_ratio": r.human_edit_ratio,
                "prompt": r.prompt_redacted,
                "commit_sha": r.commit_sha[:8],
            })
    return {"path": path, "lines": lines}


@router.get("/records")
def list_records(
    repo: str,
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(ProvenanceRecordORM)
        .where(ProvenanceRecordORM.repo == repo)
        .order_by(ProvenanceRecordORM.file_path, ProvenanceRecordORM.line_start)   # stable pages
        .limit(limit).offset(offset)
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
