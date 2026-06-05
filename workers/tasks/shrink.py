from __future__ import annotations

from backend.app.celery_app import celery


@celery.task(name="gitly.shrink.run")
def run_shrink(job_id: str, request: dict) -> dict:
    """Async shrink: run the real engine on a local repo path — plan → materialize → verify
    (`tree(base+slices) == tree(head)`). Cloning from a GitHub URL + opening PRs on a webhook
    is the GitHub-App milestone; this runs the actual engine so the queue path is no longer a
    no-op."""
    from backend.app.engines.shrink.planner.planner import PlanOptions
    from backend.app.engines.shrink.service import shrink

    repo = request.get("repo")
    if not repo:
        return {"job_id": job_id, "status": "error", "error": "no repo path provided"}
    base = request.get("base", "main")
    head = request.get("head", "HEAD")
    opts = PlanOptions(max_lines=request["max_lines"]) if request.get("max_lines") else None
    try:
        res = shrink(repo, base, head, opts=opts, write_refs=bool(request.get("write_refs")))
    except Exception as e:
        return {"job_id": job_id, "status": "error", "error": str(e)}
    return {
        "job_id": job_id,
        "status": "complete" if res.completeness_ok else "incomplete",
        "completeness_ok": res.completeness_ok,
        "original_lines": res.original_lines,
        "original_files": res.original_files,
        "slices": [s.model_dump() for s in res.slices],
    }
