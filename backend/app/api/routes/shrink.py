from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/shrink", tags=["shrink"])


class ShrinkRequest(BaseModel):
    repo: str
    base: str = "main"
    head: str = "HEAD"
    max_lines: int = 400          # lands in the evidence-backed 200–400 LOC band


@router.post("/jobs")
def create_shrink_job(req: ShrinkRequest):
    """Enqueue a shrink job. Engine ports from pr-shrinker (see MIGRATION.md)."""
    job_id = uuid.uuid4().hex
    try:
        from workers.tasks.shrink import run_shrink

        run_shrink.delay(job_id, req.model_dump())
        queued = True
    except Exception:
        queued = False            # broker offline in local dev — degrade gracefully
    return {"job_id": job_id, "queued": queued, "note": "engine port pending — MIGRATION.md"}
