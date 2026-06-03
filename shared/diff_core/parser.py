"""Shared unified-diff parser — the single kernel both `shrink` and `lens` build on.

Today a thin facade over `unidiff`. Port targets to merge in here (see MIGRATION.md):
  - pr-shrinker:    src/prshrink/engine/diff/parse.py   (classifies rename/binary/mode)
  - pr-visual-diff: backend/app/diff/parser.py          (robust to no-newline markers)
Unifying them means provenance, shrinking, and clustering share one diff model.
"""
from __future__ import annotations

from shared.schema.common import ChangeKind, DiffFile, Hunk, ParsedDiff

try:
    from unidiff import PatchSet
except ImportError:  # keep the kernel importable before deps are installed
    PatchSet = None


def parse_unified_diff(diff_text: str) -> ParsedDiff:
    if PatchSet is None:
        raise RuntimeError("unidiff not installed; run `make install`")
    patch = PatchSet(diff_text)
    files: list[DiffFile] = []
    for pf in patch:
        kind = (
            ChangeKind.add if pf.is_added_file
            else ChangeKind.delete if pf.is_removed_file
            else ChangeKind.rename if pf.is_rename
            else ChangeKind.binary if pf.is_binary_file
            else ChangeKind.modify
        )
        hunks = [
            Hunk(
                file_path=pf.path,
                old_start=h.source_start,
                old_lines=h.source_length,
                new_start=h.target_start,
                new_lines=h.target_length,
                text=str(h),
            )
            for h in pf
        ]
        files.append(DiffFile(path=pf.path, change_kind=kind, hunks=hunks))
    return ParsedDiff(files=files)
