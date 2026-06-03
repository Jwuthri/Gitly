"""Build a file/module dependency graph from a diff and derive an ordering.

v1 edges (heuristic): import edges (A imports a module that resolves to changed file B) and
reference edges (A references a symbol that changed file B defines). We condense
strongly-connected components and topologically order so prerequisites come first.
Completeness does not depend on any of this being correct — it only shapes the grouping.
"""
from __future__ import annotations

import networkx as nx

from ..diff.models import Diff
from .analyzer import HeuristicAnalyzer


def symbol_providers(diff: Diff) -> dict[str, set[str]]:
    """symbol name -> set of changed file paths that define it."""
    providers: dict[str, set[str]] = {}
    for f in diff.files:
        for h in f.hunks:
            for sym in h.symbols_defined:
                providers.setdefault(sym, set()).add(f.path)
    return providers


def _resolve_import(spec: str, changed_paths: set[str]) -> str | None:
    """Best-effort: match an import specifier to a changed file by path suffix."""
    norm = spec.lstrip(".").replace(".", "/").strip("/")
    if not norm:
        return None
    for p in changed_paths:
        stem = p.rsplit(".", 1)[0]
        if stem.endswith(norm) or stem.split("/")[-1] == norm.split("/")[-1]:
            return p
    return None


def build_file_graph(diff: Diff, analyzer: HeuristicAnalyzer | None = None) -> nx.DiGraph:
    """Directed graph over changed file paths; edge u -> v means 'u should come before v'."""
    analyzer = analyzer or HeuristicAnalyzer()
    changed = {f.path for f in diff.files}
    providers = symbol_providers(diff)
    g = nx.DiGraph()
    g.add_nodes_from(changed)

    for f in diff.files:
        for h in f.hunks:
            for ref in h.symbols_referenced:
                for provider in providers.get(ref, set()):
                    if provider != f.path:
                        g.add_edge(provider, f.path)  # provider before f
        for spec in analyzer.imports(f.path, f.hunks):
            target = _resolve_import(spec, changed)
            if target and target != f.path:
                g.add_edge(target, f.path)  # imported file before importer
    return g


def topo_file_order(diff: Diff, analyzer: HeuristicAnalyzer | None = None) -> list[str]:
    """Topological order of changed files (prerequisites first), SCC-safe and stable."""
    g = build_file_graph(diff, analyzer)
    condensed = nx.condensation(g)  # DAG of SCCs
    order: list[str] = []
    for scc_node in nx.lexicographical_topological_sort(condensed):
        members = sorted(condensed.nodes[scc_node]["members"])
        order.extend(members)
    seen = set(order)
    for f in diff.files:
        if f.path not in seen:
            order.append(f.path)
            seen.add(f.path)
    return order
