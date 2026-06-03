"""Shared diff model — the small, framework-free vocabulary that `shrink`, `lens`,
and `trace` all speak. Both source repos parse unified diffs into near-identical
shapes; this is the single canonical version they converge on."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class ChangeKind(str, Enum):
    add = "add"
    modify = "modify"
    delete = "delete"
    rename = "rename"
    binary = "binary"
    mode = "mode"


class Hunk(BaseModel):
    file_path: str
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    text: str               # full unified-diff hunk, including the @@ header


class DiffFile(BaseModel):
    path: str
    change_kind: ChangeKind
    hunks: list[Hunk] = []


class ParsedDiff(BaseModel):
    files: list[DiffFile] = []

    @property
    def changed_lines(self) -> int:
        return sum(
            sum(1 for ln in h.text.splitlines() if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---")))
            for f in self.files
            for h in f.hunks
        )
