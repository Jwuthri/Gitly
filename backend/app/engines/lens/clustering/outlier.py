"""Layer 4 — Outlier surfacing. Given a finished cluster, flag the sites that *almost*
match its dominant pattern but deviate ("47 sites renamed X→Y, but 3 renamed X→Z")."""
from __future__ import annotations

from collections import Counter

from ..diff.parser import ParsedHunk
from ..models import Cluster, Outlier


def dominant_value(values: list[str]) -> str | None:
    """The most common value; ties broken by earliest appearance. None if empty."""
    if not values:
        return None
    counts = Counter(values)
    best = max(counts.values())
    for v in values:
        if counts[v] == best:
            return v
    return None  # unreachable


def find_outliers(cluster: Cluster, hunks: dict[str, ParsedHunk]) -> list[Outlier]:
    """Return the sites in `cluster` that deviate from its dominant substitution.
    Only substitution clusters (sites with from/to bindings) are analyzed."""
    pairs = [
        (s, s.binding["from"], s.binding["to"])
        for s in cluster.sites
        if s.binding and "from" in s.binding and "to" in s.binding
    ]
    if len(pairs) < 2:
        return []

    dominant = dominant_value([to for _s, _f, to in pairs])
    outliers: list[Outlier] = []
    for site, frm, to in pairs:
        if to != dominant:
            outliers.append(
                Outlier(
                    hunk_id=site.hunk_id,
                    reason=f"renames `{frm}` to `{to}` instead of `{dominant}`",
                    expected=f"{frm} → {dominant}",
                    found=f"{frm} → {to}",
                )
            )
    return outliers
