"""High-level shrink engine API. The single entry point the CLI and the API call.

    plan_split(repo, base, head)  -> (Diff, SlicePlan)        # propose, no writes
    shrink(repo, base, head, ...) -> ShrinkResult             # propose + materialize + verify

Pure with respect to the outside world: it touches only the given git repository. No
GitHub, no web, no database.
"""
from __future__ import annotations

from pydantic import BaseModel

from .diff.materialize import MaterializeResult, materialize
from .diff.models import Diff, SlicePlan
from .diff.parse import parse_pr
from .planner.labeler import get_labeler
from .planner.planner import PlanOptions, plan


class SliceSummary(BaseModel):
    order: int
    title: str
    intent: str
    lines: int
    files: int
    depends_on: list[int]


class ShrinkResult(BaseModel):
    repo: str
    base_ref: str
    head_ref: str
    original_lines: int
    original_files: int
    strategy: str
    slices: list[SliceSummary]
    notes: list[str]
    materialized: MaterializeResult | None = None

    @property
    def completeness_ok(self) -> bool:
        return self.materialized is not None and self.materialized.completeness.ok


def _summaries(plan_obj: SlicePlan) -> list[SliceSummary]:
    return [
        SliceSummary(
            order=s.order,
            title=s.title,
            intent=s.intent,
            lines=s.line_count,
            files=s.file_count,
            depends_on=s.depends_on,
        )
        for s in plan_obj.slices
    ]


def plan_split(
    repo: str,
    base_ref: str,
    head_ref: str,
    *,
    opts: PlanOptions | None = None,
    prefer_llm: bool = True,
) -> tuple[Diff, SlicePlan]:
    diff = parse_pr(repo, base_ref, head_ref)
    proposed = plan(diff, opts)
    proposed = get_labeler(prefer_llm).label(diff, proposed)
    return diff, proposed


def shrink(
    repo: str,
    base_ref: str,
    head_ref: str,
    *,
    opts: PlanOptions | None = None,
    out_prefix: str = "shrink/",
    write_refs: bool = False,
    prefer_llm: bool = True,
) -> ShrinkResult:
    diff, proposed = plan_split(repo, base_ref, head_ref, opts=opts, prefer_llm=prefer_llm)
    mat = materialize(repo, diff, proposed, out_prefix=out_prefix, write_refs=write_refs)
    return ShrinkResult(
        repo=repo,
        base_ref=base_ref,
        head_ref=head_ref,
        original_lines=diff.total_lines,
        original_files=diff.total_files,
        strategy=proposed.strategy,
        slices=_summaries(proposed),
        notes=proposed.notes,
        materialized=mat,
    )
