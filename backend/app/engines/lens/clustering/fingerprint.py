"""Layer 1 — structural fingerprinting (token substitutions).

Groups hunks whose change is the *same token substitution* — a rename, type swap, or
import-path migration applied across many sites — into one high-confidence cluster,
regardless of surrounding code. This collapses "47 nearly-identical hunks" into one card.
"""
from __future__ import annotations

from collections import defaultdict

from ._edit import hunk_substitution, is_string_token
from .naming import anchor_line, label_for_site
from .outlier import dominant_value
from ..diff.parser import ParsedDiff, ParsedFile, ParsedHunk
from ..models import Cluster, ClusterKind, Confidence, Site

# Clustering is about *repetition*: a one-off substitution stays an ordinary edit.
MIN_SITES = 2


def _disp(tok: str) -> str:
    """Display form of a token: strip surrounding string quotes if present."""
    if is_string_token(tok):
        return tok[1:-1]
    return tok


class SubstitutionClusterer:
    """Cluster hunks that apply the same token substitution. Engine ``Clusterer``."""

    name = "substitution"

    def cluster(self, diff: ParsedDiff, claimed: set[str]) -> list[Cluster]:
        file_by_id: dict[str, ParsedFile] = {}
        hunk_by_id: dict[str, ParsedHunk] = {}
        subs_by_id: dict[str, frozenset[tuple[str, str]]] = {}

        for file in diff.files:
            for hunk in file.hunks:
                if hunk.id in claimed:
                    continue
                subs = hunk_substitution(hunk)
                if subs is None:
                    continue
                subs_by_id[hunk.id] = subs
                file_by_id[hunk.id] = file
                hunk_by_id[hunk.id] = hunk

        # Bucket: single-token subs by their old token; multi-token by exact set.
        single: dict[str, list[str]] = defaultdict(list)
        multi: dict[frozenset[tuple[str, str]], list[str]] = defaultdict(list)
        for hid, subs in subs_by_id.items():
            if len(subs) == 1:
                (old, _new) = next(iter(subs))
                single[old].append(hid)
            else:
                multi[subs].append(hid)

        clusters: list[Cluster] = []
        for old, hids in single.items():
            if len(hids) >= MIN_SITES:
                clusters.append(self._single_cluster(old, hids, subs_by_id, file_by_id, hunk_by_id))
        for subs, hids in multi.items():
            if len(hids) >= MIN_SITES:
                clusters.append(self._multi_cluster(subs, hids, file_by_id, hunk_by_id))
        return clusters

    @staticmethod
    def _sorted_sites(
        hids: list[str], file_by_id: dict[str, ParsedFile], hunk_by_id: dict[str, ParsedHunk]
    ) -> list[str]:
        return sorted(hids, key=lambda h: (file_by_id[h].path, anchor_line(hunk_by_id[h])))

    def _single_cluster(
        self,
        old: str,
        hids: list[str],
        subs_by_id: dict[str, frozenset[tuple[str, str]]],
        file_by_id: dict[str, ParsedFile],
        hunk_by_id: dict[str, ParsedHunk],
    ) -> Cluster:
        ordered = self._sorted_sites(hids, file_by_id, hunk_by_id)
        new_by_id = {h: next(iter(subs_by_id[h]))[1] for h in ordered}
        dominant = dominant_value([new_by_id[h] for h in ordered]) or new_by_id[ordered[0]]

        sites = [
            Site(
                hunk_id=h,
                file=file_by_id[h].path,
                line=anchor_line(hunk_by_id[h]),
                label=label_for_site(file_by_id[h], hunk_by_id[h]),
                binding={"from": old, "to": new_by_id[h]},
            )
            for h in ordered
        ]
        rep = next((h for h in ordered if new_by_id[h] == dominant), ordered[0])

        is_import = is_string_token(old)
        kind = ClusterKind.import_migration if is_import else ClusterKind.rename
        verb = "Migrated import" if is_import else "Renamed"
        title = f"{verb} `{_disp(old)}` → `{_disp(dominant)}`"
        n_files = len({file_by_id[h].path for h in ordered})
        desc = f"Same substitution at {len(ordered)} sites across {n_files} files."

        return Cluster(
            id="",
            kind=kind,
            title=title,
            description=desc,
            confidence=Confidence.high,
            confidence_reason=f"structural fingerprint: identical token substitution at {len(ordered)} sites",
            representative_hunk_id=rep,
            sites=sites,
            site_count=len(sites),
            file_count=n_files,
            outliers=[],
            tags=[],
        )

    def _multi_cluster(
        self,
        subs: frozenset[tuple[str, str]],
        hids: list[str],
        file_by_id: dict[str, ParsedFile],
        hunk_by_id: dict[str, ParsedHunk],
    ) -> Cluster:
        ordered = self._sorted_sites(hids, file_by_id, hunk_by_id)
        mapping = dict(sorted(subs))
        sites = [
            Site(
                hunk_id=h,
                file=file_by_id[h].path,
                line=anchor_line(hunk_by_id[h]),
                label=label_for_site(file_by_id[h], hunk_by_id[h]),
                binding={k: v for k, v in mapping.items()},
            )
            for h in ordered
        ]
        joined = ", ".join(f"`{_disp(o)}` → `{_disp(n)}`" for o, n in mapping.items())
        n_files = len({file_by_id[h].path for h in ordered})
        return Cluster(
            id="",
            kind=ClusterKind.rename,
            title=f"Renamed {joined}",
            description=f"Same {len(mapping)} substitutions at {len(ordered)} sites.",
            confidence=Confidence.high,
            confidence_reason=f"structural fingerprint: identical substitution set at {len(ordered)} sites",
            representative_hunk_id=ordered[0],
            sites=sites,
            site_count=len(sites),
            file_count=n_files,
            outliers=[],
            tags=[],
        )


def fingerprint(hunks: list[ParsedHunk]) -> list[Cluster]:
    """Functional entry point. Runs ``SubstitutionClusterer`` over a bare hunk list."""
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
    return SubstitutionClusterer().cluster(ParsedDiff(files=files), claimed=set())
