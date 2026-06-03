"""Layer 2 — template matching (token insertions).

Catches the "insert the same thing everywhere" edit that is not a substitution: adding a
first parameter to every handler (``ctx context.Context``), wrapping calls in ``await``,
prepending a decorator. Hunks whose change is the *same inserted token run* cluster at
medium confidence, with the inserted text bound on each site.
"""
from __future__ import annotations

from collections import defaultdict

from ._edit import hunk_insertion, pretty_run
from .naming import anchor_line, label_for_site
from ..diff.parser import ParsedDiff, ParsedFile, ParsedHunk
from ..models import Cluster, ClusterKind, Confidence, Site

MIN_SITES = 2


def _title_for_insertion(runs: tuple[str, ...]) -> tuple[str, ClusterKind]:
    pretties = [pretty_run(r) for r in runs]
    joined = " + ".join(p.rstrip(", ") for p in pretties)
    multi_token = any(" " in p for p in pretties)
    if multi_token:
        return f"Added parameter `{joined}`", ClusterKind.signature_change
    return f"Added `{joined}`", ClusterKind.boilerplate_insertion


class InsertionTemplateClusterer:
    """Cluster hunks that insert the same token run. Engine ``Clusterer``."""

    name = "template-insertion"

    def cluster(self, diff: ParsedDiff, claimed: set[str]) -> list[Cluster]:
        file_by_id: dict[str, ParsedFile] = {}
        hunk_by_id: dict[str, ParsedHunk] = {}
        sig_by_id: dict[str, tuple[str, ...]] = {}

        for file in diff.files:
            for hunk in file.hunks:
                if hunk.id in claimed:
                    continue
                sig = hunk_insertion(hunk)
                if sig is None:
                    continue
                sig_by_id[hunk.id] = sig
                file_by_id[hunk.id] = file
                hunk_by_id[hunk.id] = hunk

        groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
        for hid, sig in sig_by_id.items():
            groups[sig].append(hid)

        clusters: list[Cluster] = []
        for sig, hids in groups.items():
            if len(hids) < MIN_SITES:
                continue
            ordered = sorted(hids, key=lambda h: (file_by_id[h].path, anchor_line(hunk_by_id[h])))
            inserted = "; ".join(pretty_run(r) for r in sig)
            sites = [
                Site(
                    hunk_id=h,
                    file=file_by_id[h].path,
                    line=anchor_line(hunk_by_id[h]),
                    label=label_for_site(file_by_id[h], hunk_by_id[h]),
                    binding={"inserted": inserted},
                )
                for h in ordered
            ]
            title, kind = _title_for_insertion(sig)
            n_files = len({file_by_id[h].path for h in ordered})
            clusters.append(
                Cluster(
                    id="",
                    kind=kind,
                    title=title,
                    description=f"Same insertion at {len(ordered)} sites across {n_files} files.",
                    confidence=Confidence.medium,
                    confidence_reason=f"template match: identical insertion at {len(ordered)} sites",
                    representative_hunk_id=ordered[0],
                    sites=sites,
                    site_count=len(sites),
                    file_count=n_files,
                    outliers=[],
                    tags=[],
                )
            )
        return clusters


def templatize(hunks: list[ParsedHunk]) -> list[Cluster]:
    """Functional entry point. Runs ``InsertionTemplateClusterer`` over a bare hunk list."""
    from ..models import FileStatus

    by_file: dict[str, list[ParsedHunk]] = defaultdict(list)
    for h in hunks:
        by_file[h.file].append(h)
    files = [
        ParsedFile(
            path=path,
            old_path=None,
            status=FileStatus.modified,
            language=hs[0].language,
            is_generated=False,
            is_binary=False,
            additions=0,
            deletions=0,
            hunks=hs,
        )
        for path, hs in by_file.items()
    ]
    return InsertionTemplateClusterer().cluster(ParsedDiff(files=files), claimed=set())
