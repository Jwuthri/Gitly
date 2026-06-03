from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.engines.lens.diff.parser import DiffParseError
from backend.app.engines.lens.engine import ENGINE_VERSION, analyze, make_source
from backend.app.engines.lens.models import AnalysisResult, SourceType

router = APIRouter(prefix="/lens", tags=["lens"])


class AnalyzeRequest(BaseModel):
    diff: str


@router.post("/analyze", response_model=AnalysisResult)
def analyze_endpoint(body: AnalyzeRequest):
    """Cluster a unified diff into conceptual changes — renames, import migrations, and
    repeated insertions collapse into single cards, with deviating sites flagged as
    outliers. Powered by the lens engine (ported from pr-visual-diff)."""
    if not body.diff or not body.diff.strip():
        raise HTTPException(status_code=400, detail="No diff provided. Send a unified diff in `diff`.")
    try:
        return analyze(body.diff, source=make_source(SourceType.raw_diff))
    except DiffParseError as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse diff: {exc}")


@router.get("/engine")
def engine_info():
    return {"engine_version": ENGINE_VERSION}
