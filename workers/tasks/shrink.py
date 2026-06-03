from __future__ import annotations

from backend.app.celery_app import celery


@celery.task(name="gitly.shrink.run")
def run_shrink(job_id: str, request: dict) -> dict:
    """Async shrink. Port the engine + orchestrator from pr-shrinker (MIGRATION.md):
    clone/resolve refs -> plan slices -> materialize stack -> verify completeness
    (tree(base+slices)==tree(head)) -> open stacked PRs. Registered no-op for now so the
    queue path is wired end-to-end."""
    return {"job_id": job_id, "status": "noop", "note": "engine port pending"}
