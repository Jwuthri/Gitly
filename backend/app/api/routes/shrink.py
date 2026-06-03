from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/shrink", tags=["shrink"])

# Shrink "strength" presets — gentle = fewest/largest PRs, aggressive = many small ones.
STRENGTH: dict[str, dict[str, int]] = {
    "gentle":     {"max_lines": 1500, "min_lines": 300, "max_slices": 2},
    "balanced":   {"max_lines": 400,  "min_lines": 40,  "max_slices": 6},
    "aggressive": {"max_lines": 120,  "min_lines": 1,   "max_slices": 20},
}


class PlanRequest(BaseModel):
    diff: str
    strength: str = "balanced"
    max_lines: int | None = None    # optional override of the strength preset


@router.post("/analyze")
def analyze(body: PlanRequest):
    """Propose a slice plan from a raw unified diff (no repo needed). `strength` controls how
    aggressively it splits. Materialization + completeness verification require a local repo
    (use the gitly CLI)."""
    from backend.app.engines.shrink.diff.parse import parse_patch_text
    from backend.app.engines.shrink.planner.labeler import HeuristicLabeler
    from backend.app.engines.shrink.planner.planner import PlanOptions, plan as make_plan

    if not body.diff or not body.diff.strip():
        raise HTTPException(status_code=400, detail="No diff provided. Send a unified diff in `diff`.")
    strength = body.strength if body.strength in STRENGTH else "balanced"
    preset = dict(STRENGTH[strength])
    if body.max_lines:
        preset["max_lines"] = body.max_lines
    try:
        diff = parse_patch_text(body.diff, "base", "head", "base", "head")
        p = make_plan(diff, PlanOptions(**preset))
        p = HeuristicLabeler().label(diff, p)
    except Exception as exc:  # unidiff is strict about hunk line counts
        raise HTTPException(status_code=400, detail=f"Could not parse diff: {exc}")
    return {
        "original_lines": diff.total_lines,
        "original_files": diff.total_files,
        "strategy": p.strategy,
        "strength": strength,
        "slices": [
            {
                "order": s.order,
                "title": s.title,
                "intent": s.intent,
                "lines": s.line_count,
                "files": s.file_count,
                "depends_on": s.depends_on,
                "hunks": len(s.hunk_ids) + len(s.atomic_paths),
            }
            for s in p.slices
        ],
        "notes": p.notes,
        "note": "plan only — materialization + tree-equality verification require a repo (gitly CLI).",
    }


class ShrinkRequest(BaseModel):
    repo: str
    base: str = "main"
    head: str = "HEAD"
    max_lines: int = 400          # lands in the evidence-backed 200–400 LOC band


@router.post("/jobs")
def create_shrink_job(req: ShrinkRequest):
    """Enqueue an async shrink job (clone → plan → materialize → verify → open stacked PRs).
    Used by the hosted GitHub-App flow; for a local repo, prefer the gitly CLI."""
    job_id = uuid.uuid4().hex
    try:
        from workers.tasks.shrink import run_shrink

        run_shrink.delay(job_id, req.model_dump())
        queued = True
    except Exception:
        queued = False            # broker offline in local dev — degrade gracefully
    return {"job_id": job_id, "queued": queued}
