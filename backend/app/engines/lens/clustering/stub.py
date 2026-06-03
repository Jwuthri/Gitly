"""Stub clusterer — ``OneHunkPerClusterClusterer``.

Emits exactly one ``low``-confidence cluster per hunk and is placed **last** in
``engine.PIPELINE`` so it claims every hunk no upstream layer grabbed — guaranteeing the
partition invariant (every hunk lands in exactly one cluster).
"""
from __future__ import annotations

from .naming import anchor_line, label_for_site, title_for_hunk
from ..diff.parser import ParsedDiff, ParsedFile, ParsedHunk
from ..models import Cluster, ClusterKind, Confidence, FileStatus, Site

STUB_CONFIDENCE_REASON = "stub: one hunk per cluster - real clustering not yet implemented"


def _kind_for_file(file: ParsedFile) -> ClusterKind:
    if file.status == FileStatus.added:
        return ClusterKind.new_file
    if file.status == FileStatus.deleted:
        return ClusterKind.deleted_file
    return ClusterKind.ungrouped


class OneHunkPerClusterClusterer:
    """Claim every still-unclaimed hunk as its own ``low``-confidence cluster."""

    name = "stub"

    def cluster(self, diff: ParsedDiff, claimed: set[str]) -> list[Cluster]:
        clusters: list[Cluster] = []
        for file in diff.files:
            for hunk in file.hunks:
                if hunk.id in claimed:
                    continue
                clusters.append(self._cluster_for_hunk(file, hunk))
        return clusters

    @staticmethod
    def _cluster_for_hunk(file: ParsedFile, hunk: ParsedHunk) -> Cluster:
        site = Site(
            hunk_id=hunk.id,
            file=file.path,
            line=anchor_line(hunk),
            label=label_for_site(file, hunk),
            binding=None,
        )
        return Cluster(
            id="",
            kind=_kind_for_file(file),
            title=title_for_hunk(file, hunk),
            description=None,
            confidence=Confidence.low,
            confidence_reason=STUB_CONFIDENCE_REASON,
            representative_hunk_id=hunk.id,
            sites=[site],
            site_count=1,
            file_count=1,
            outliers=[],
            tags=[],
        )
