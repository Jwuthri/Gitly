from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from shared.diff_core.parser import parse_unified_diff

router = APIRouter(prefix="/lens", tags=["lens"])


class AnalyzeRequest(BaseModel):
    diff: str


@router.post("/analyze")
def analyze(req: AnalyzeRequest):
    """Cluster a diff into conceptual cards. The clustering engine ports from
    pr-visual-diff; for now we parse with the shared kernel and return the file/hunk
    skeleton so the contract and wiring are live."""
    parsed = parse_unified_diff(req.diff)
    return {
        "files": len(parsed.files),
        "changed_lines": parsed.changed_lines,
        "clusters": "engine port pending — MIGRATION.md (../pr-visual-diff)",
        "skeleton": [
            {"path": f.path, "change": f.change_kind.value, "hunks": len(f.hunks)}
            for f in parsed.files
        ],
    }
