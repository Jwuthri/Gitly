from __future__ import annotations

from backend.app.celery_app import celery


@celery.task(name="gitly.trace.sync")
def sync_provenance(repo: str, records: list[dict]) -> dict:
    """Async provenance sync (opt-in): persist commit-bound records to Postgres for the
    dashboard. Prompts are redacted at capture time; we re-redact defensively here."""
    from backend.app.db.models import ProvenanceRecordORM
    from backend.app.db.session import SessionLocal
    from backend.app.security.secret_firewall import redact

    cols = {c.name for c in ProvenanceRecordORM.__table__.columns}
    db = SessionLocal()
    try:
        for r in records:
            if r.get("prompt_redacted"):
                r["prompt_redacted"] = redact(r["prompt_redacted"])
            db.merge(ProvenanceRecordORM(**{k: v for k, v in r.items() if k in cols}))
        db.commit()
        return {"repo": repo, "ingested": len(records)}
    finally:
        db.close()
