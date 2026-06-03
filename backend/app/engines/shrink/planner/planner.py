"""Turn a `Diff` into an ordered `SlicePlan`.

The hybrid v1 strategy: classify each change by semantic category, group by module, order
by category then dependency topology, then enforce size bounds (split oversized groups,
merge tiny ones). Slice titles/intents are placeholders here and are refined by the labeler.

Whatever this produces, the materializer guarantees the slices sum to the original head —
so a mediocre grouping yields awkward-but-correct PRs, never a broken or lossy stack.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from ..diff.models import Diff, Slice, SlicePlan
from ..graph.analyzer import HeuristicAnalyzer
from ..graph.depgraph import topo_file_order
from .classify import Category, classify, is_generated, module_of


class PlanOptions(BaseModel):
    max_lines: int = 400
    min_lines: int = 40
    max_slices: int = 8
    module_depth: int = 2
    strategy: str = "hybrid"


@dataclass
class _Unit:
    kind: str  # "hunk" | "atomic"
    ref: str  # hunk id or atomic file path
    file: str
    category: Category
    module: str
    size: int
    defines: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    generated: bool = False


@dataclass
class _Group:
    category: Category
    module: str
    units: list[_Unit]
    generated: bool = False

    @property
    def size(self) -> int:
        return sum(u.size for u in self.units)

    @property
    def hunk_ids(self) -> list[str]:
        return [u.ref for u in self.units if u.kind == "hunk"]

    @property
    def atomic_paths(self) -> list[str]:
        return [u.ref for u in self.units if u.kind == "atomic"]

    @property
    def files(self) -> set[str]:
        return {u.file for u in self.units}

    @property
    def defines(self) -> set[str]:
        return {s for u in self.units for s in u.defines}

    @property
    def references(self) -> set[str]:
        return {s for u in self.units for s in u.references}


def _units(diff: Diff, opts: PlanOptions) -> list[_Unit]:
    units: list[_Unit] = []
    for f in diff.files:
        cat = classify(f)
        mod = module_of(f.path, opts.module_depth)
        gen = is_generated(f.path)
        if f.is_atomic:
            units.append(
                _Unit("atomic", f.path, f.path, cat, mod, max(f.added + f.removed, 1), generated=gen)
            )
        for h in f.hunks:
            units.append(
                _Unit("hunk", h.id, f.path, cat, mod, h.size, list(h.symbols_defined),
                      list(h.symbols_referenced), generated=gen)
            )
    return units


def _initial_groups(units: list[_Unit], file_rank: dict[str, int]) -> list[_Group]:
    buckets: dict[tuple[int, str, bool], _Group] = {}
    for u in units:
        key = (int(u.category), u.module, u.generated)
        if key not in buckets:
            buckets[key] = _Group(u.category, u.module, [], u.generated)
        buckets[key].units.append(u)

    def sort_key(g: _Group):
        rank = min((file_rank.get(u.file, 1_000_000) for u in g.units), default=0)
        return (int(g.category), g.generated, rank, g.module)

    return sorted(buckets.values(), key=sort_key)


def _split_oversized(groups: list[_Group], max_lines: int) -> list[_Group]:
    out: list[_Group] = []
    for g in groups:
        if g.size <= max_lines:
            out.append(g)
            continue
        by_file: dict[str, list[_Unit]] = {}
        for u in g.units:
            by_file.setdefault(u.file, []).append(u)
        current: list[_Unit] = []
        cur_size = 0
        for _file, fus in by_file.items():
            fsize = sum(u.size for u in fus)
            if current and cur_size + fsize > max_lines:
                out.append(_Group(g.category, g.module, current, g.generated))
                current, cur_size = [], 0
            if fsize > max_lines:
                for u in fus:
                    if current and cur_size + u.size > max_lines:
                        out.append(_Group(g.category, g.module, current, g.generated))
                        current, cur_size = [], 0
                    current.append(u)
                    cur_size += u.size
            else:
                current.extend(fus)
                cur_size += fsize
        if current:
            out.append(_Group(g.category, g.module, current, g.generated))
    return out


def _merge_small(groups: list[_Group], min_lines: int, max_lines: int) -> list[_Group]:
    out: list[_Group] = []
    for g in groups:
        if (
            out
            and out[-1].category == g.category
            and out[-1].generated == g.generated
            and (out[-1].size < min_lines or g.size < min_lines)
            and out[-1].size + g.size <= max_lines
        ):
            merged = out[-1]
            merged.units.extend(g.units)
            if merged.module != g.module:
                merged.module = f"{merged.module.split(' +')[0]} +"
        else:
            out.append(_Group(g.category, g.module, list(g.units), g.generated))
    return out


def _enforce_max_slices(groups: list[_Group], max_slices: int, max_lines: int) -> list[_Group]:
    while len(groups) > max_slices:
        best_i, best_score = None, None
        for i in range(len(groups) - 1):
            same = groups[i].category == groups[i + 1].category
            score = (not same, groups[i].size + groups[i + 1].size)
            if best_score is None or score < best_score:
                best_score, best_i = score, i
        i = best_i if best_i is not None else 0
        groups[i].units.extend(groups[i + 1].units)
        del groups[i + 1]
    return groups


_CAT_LABEL = {
    Category.DEPS: "dependencies",
    Category.CONFIG: "config",
    Category.MIGRATION: "migrations",
    Category.SOURCE: "source",
    Category.TEST: "tests",
    Category.DOCS: "docs",
}


def _join(items: list[str]) -> str:
    items = list(dict.fromkeys(items))  # dedupe, keep order
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]} & {items[1]}"
    return ", ".join(items[:-1]) + f" & {items[-1]}"


def _title_for(g: _Group) -> str:
    """Title a slice from the categories/modules it actually contains — so a merged,
    multi-category slice describes everything it spans (e.g. 'Dependencies & source')."""
    cats = sorted({u.category for u in g.units})
    if g.generated:
        return "Update generated files"
    if len(cats) > 1:
        return _join([_CAT_LABEL[c] for c in cats]).capitalize()
    cat = cats[0]
    mods = sorted({u.module for u in g.units if u.module != "(root)"})
    where = "project" if not mods else _join(mods) if len(mods) <= 2 else f"{mods[0]} +{len(mods) - 1} more"
    defs = sorted(g.defines)
    if cat == Category.DEPS:
        return "Add/update dependencies"
    if cat == Category.CONFIG:
        return f"Configuration changes in {where}"
    if cat == Category.MIGRATION:
        return f"Database migration in {where}"
    if cat == Category.TEST:
        return f"Tests for {where}"
    if cat == Category.DOCS:
        return f"Update docs in {where}"
    if defs:
        lead = defs[0]
        extra = f" (+{len(defs) - 1} more)" if len(defs) > 1 else ""
        return f"Add {lead}{extra}"
    return f"Changes in {where}"


def _depends_on(groups: list[_Group]) -> list[list[int]]:
    """For each group (1-based order), the earlier groups whose defined symbols it
    references. Falls back to the previous slice."""
    deps: list[list[int]] = []
    define_owner: dict[str, int] = {}
    for idx, g in enumerate(groups, start=1):
        d: set[int] = set()
        for ref in g.references:
            owner = define_owner.get(ref)
            if owner and owner != idx:
                d.add(owner)
        if not d and idx > 1:
            d.add(idx - 1)  # linear stack fallback
        deps.append(sorted(d))
        for sym in g.defines:
            define_owner.setdefault(sym, idx)
    return deps


def plan(diff: Diff, opts: PlanOptions | None = None) -> SlicePlan:
    opts = opts or PlanOptions()
    HeuristicAnalyzer().annotate(diff)
    file_rank = {p: i for i, p in enumerate(topo_file_order(diff))}

    groups = _initial_groups(_units(diff, opts), file_rank)
    groups = _split_oversized(groups, opts.max_lines)
    groups = _merge_small(groups, opts.min_lines, opts.max_lines)
    groups = _enforce_max_slices(groups, opts.max_slices, opts.max_lines)

    deps = _depends_on(groups)
    slices: list[Slice] = []
    for i, (g, dep) in enumerate(zip(groups, deps, strict=True), start=1):
        slices.append(
            Slice(
                order=i,
                title=_title_for(g),
                intent="",
                hunk_ids=g.hunk_ids,
                atomic_paths=g.atomic_paths,
                depends_on=dep,
                line_count=g.size,
                file_count=len(g.files),
            )
        )
    notes: list[str] = []
    if any(g.generated for g in groups):
        notes.append("Some changes are to generated files; review those separately.")
    return SlicePlan(strategy=opts.strategy, slices=slices, notes=notes)
