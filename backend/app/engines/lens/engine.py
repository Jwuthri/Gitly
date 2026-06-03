"""Clustering orchestrator: ``ParsedDiff`` -> ``AnalysisResult``.

1. Run an ordered ``PIPELINE`` of clusterers; each is handed the parsed diff plus the
   hunk ids already claimed, and returns clusters for some remaining hunks. The stub runs
   last and claims everything left, so the partition invariant always holds.
2. Recompute derived fields (site_count/file_count) and run the Layer-4 outlier seam.
3. Assign ids, build files/hunks/stats, compute the content-addressed analysis id.
4. Assert the partition invariant before returning (never ship a broken payload).
"""
from __future__ import annotations

import hashlib
from typing import Protocol

from .clustering import outlier as outlier_layer
from .clustering.fingerprint import SubstitutionClusterer
from .clustering.stub import OneHunkPerClusterClusterer
from .clustering.template import InsertionTemplateClusterer
from .diff.parser import ParsedDiff, ParsedHunk, parse_diff
from .models import (
    AnalysisResult,
    Cluster,
    DiffLine,
    FileChange,
    Hunk,
    Source,
    SourceType,
    Stats,
)

ENGINE_VERSION = "fingerprint-0.2.0"


class Clusterer(Protocol):
    name: str

    def cluster(self, diff: ParsedDiff, claimed: set[str]) -> list[Cluster]:  # pragma: no cover
        ...


# Ordered pipeline. Real layers drop in *above* the stub; the stub is always last.
PIPELINE: list[Clusterer] = [
    SubstitutionClusterer(),       # Layer 1 — renames / type swaps / import migrations
    InsertionTemplateClusterer(),  # Layer 2 — added params / await wrappers / boilerplate
    OneHunkPerClusterClusterer(),  # always last: claims everything still unclaimed
]


def _normalize_diff(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")


def compute_analysis_id(diff_text: str, engine_version: str = ENGINE_VERSION) -> str:
    payload = (_normalize_diff(diff_text) + engine_version).encode("utf-8")
    return f"v_{hashlib.sha256(payload).hexdigest()[:16]}"


def _to_schema_hunk(h: ParsedHunk) -> Hunk:
    return Hunk(
        id=h.id,
        file=h.file,
        old_file=h.old_file,
        header=h.header,
        language=h.language,
        old_start=h.old_start,
        old_lines=h.old_lines,
        new_start=h.new_start,
        new_lines=h.new_lines,
        lines=[DiffLine(type=ln.type, content=ln.content, old_no=ln.old_no, new_no=ln.new_no) for ln in h.lines],
    )


def _run_pipeline(diff: ParsedDiff) -> list[Cluster]:
    valid_hunk_ids = {h.id for h in diff.all_hunks}
    claimed: set[str] = set()
    out: list[Cluster] = []

    for stage in PIPELINE:
        produced = stage.cluster(diff, set(claimed))
        for cluster in produced:
            kept_sites = [s for s in cluster.sites if s.hunk_id in valid_hunk_ids and s.hunk_id not in claimed]
            if not kept_sites:
                continue
            cluster.sites = kept_sites
            for s in kept_sites:
                claimed.add(s.hunk_id)
            out.append(cluster)

    return out


def _finalize_cluster(cluster: Cluster, cid: str, hunk_map: dict[str, ParsedHunk]) -> Cluster:
    cluster.id = cid
    cluster.site_count = len(cluster.sites)
    cluster.file_count = len({s.file for s in cluster.sites})
    site_hunk_ids = {s.hunk_id for s in cluster.sites}
    if cluster.representative_hunk_id not in site_hunk_ids:
        cluster.representative_hunk_id = cluster.sites[0].hunk_id
    cluster.outliers = outlier_layer.find_outliers(cluster, hunk_map)
    return cluster


def analyze(diff_text: str, source: Source, title: str | None = None) -> AnalysisResult:
    """Parse ``diff_text`` and assemble a fully-populated ``AnalysisResult``.
    Raises ``DiffParseError`` if the text is not a valid diff (the API turns that into 400)."""
    parsed = parse_diff(diff_text)
    warnings: list[str] = []

    parser_hunks: dict[str, ParsedHunk] = {h.id: h for h in parsed.all_hunks}

    raw_clusters = _run_pipeline(parsed)
    clusters = [_finalize_cluster(c, f"c{idx}", parser_hunks) for idx, c in enumerate(raw_clusters)]

    files = [
        FileChange(
            path=f.path,
            old_path=f.old_path,
            status=f.status,
            language=f.language,
            is_generated=f.is_generated,
            is_binary=f.is_binary,
            additions=f.additions,
            deletions=f.deletions,
            hunk_ids=f.hunk_ids,
        )
        for f in parsed.files
    ]
    hunks: dict[str, Hunk] = {h.id: _to_schema_hunk(h) for h in parsed.all_hunks}

    for f in parsed.files:
        if f.is_generated:
            warnings.append(f"generated/lock file collapsed: {f.path}")

    stats = Stats(
        files_changed=len(files),
        lines_added=sum(f.additions for f in files),
        lines_removed=sum(f.deletions for f in files),
        hunk_count=len(hunks),
        cluster_count=len(clusters),
    )

    result = AnalysisResult(
        id=compute_analysis_id(diff_text),
        engine_version=ENGINE_VERSION,
        source=source,
        title=title,
        stats=stats,
        files=files,
        hunks=hunks,
        clusters=clusters,
        warnings=warnings,
    )

    _assert_partition(result)
    return result


def _assert_partition(result: AnalysisResult) -> None:
    all_hunk_ids = set(result.hunks.keys())
    seen: list[str] = []
    for cluster in result.clusters:
        site_hunk_ids = [s.hunk_id for s in cluster.sites]
        seen.extend(site_hunk_ids)
        assert cluster.representative_hunk_id in set(site_hunk_ids), (
            f"cluster {cluster.id} representative {cluster.representative_hunk_id} not in its sites"
        )
        assert cluster.site_count == len(cluster.sites), f"cluster {cluster.id} site_count mismatch"
        assert cluster.file_count == len({s.file for s in cluster.sites}), f"cluster {cluster.id} file_count mismatch"

    seen_set = set(seen)
    assert len(seen) == len(seen_set), "partition violated: a hunk appears in more than one cluster"
    assert seen_set == all_hunk_ids, f"partition violated: clustered hunks {seen_set} != all hunks {all_hunk_ids}"
    assert result.stats.cluster_count == len(result.clusters), "stats.cluster_count mismatch"
    assert result.stats.hunk_count == len(result.hunks), "stats.hunk_count mismatch"


def make_source(type_: SourceType, ref: str | None = None) -> Source:
    return Source(type=type_, ref=ref, repo=None, head_sha=None)
