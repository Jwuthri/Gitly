"""Core data models for the shrink engine.

These are deliberately pure: no GitHub, no web, no database. A `Diff` is parsed from
git, partitioned into a `SlicePlan`, materialized into a commit stack, and verified.

The atomic unit is the **hunk**. Binary files, renames, mode changes, and deletions are
not line-hunks; they are represented as `FileChange`s with `change_type` != MODIFY and an
empty `hunks` list, and are handled atomically at materialization time.
"""
from __future__ import annotations

import hashlib
from enum import StrEnum

from pydantic import BaseModel, Field


class ChangeType(StrEnum):
    MODIFY = "modify"
    ADD = "add"
    DELETE = "delete"
    RENAME = "rename"
    COPY = "copy"
    BINARY = "binary"
    MODE = "mode"


class Hunk(BaseModel):
    """A single disjoint line-range change within one file.

    `text` is the verbatim patch text from the `@@` header to the end of the hunk,
    suitable for re-emission into a `git apply`-able patch.
    """

    file_path: str  # path in head (the "b/" side)
    hunk_index: int  # 0-based index within the file's hunk list
    source_start: int  # 1-based start line in the base file
    source_length: int  # number of base lines this hunk consumes (context + removed)
    target_start: int
    target_length: int
    added: int = 0
    removed: int = 0
    text: str  # verbatim hunk text, "@@ ... @@\n" + body

    # Annotations filled in by later stages (do not affect completeness):
    symbols_defined: list[str] = Field(default_factory=list)
    symbols_referenced: list[str] = Field(default_factory=list)
    commit_hint: str | None = None

    @property
    def id(self) -> str:
        digest = hashlib.sha1(
            f"{self.file_path}\0{self.source_start}\0{self.source_length}\0{self.text}".encode()
        ).hexdigest()[:12]
        return f"{self.file_path}@{self.source_start}:{digest}"

    @property
    def size(self) -> int:
        return self.added + self.removed


class FileChange(BaseModel):
    """All changes to a single file path."""

    path: str  # path in head (new path)
    old_path: str | None = None  # path in base, differs from `path` on rename/copy
    change_type: ChangeType
    header_text: str = ""  # patch text before the first @@ (diff --git, index, ---, +++)
    hunks: list[Hunk] = Field(default_factory=list)

    @property
    def is_atomic(self) -> bool:
        """True if this file is reconciled wholesale against head (not via line hunks):
        binary files, and any change with no line hunks (pure rename, mode-only)."""
        return self.change_type == ChangeType.BINARY or not self.hunks

    @property
    def added(self) -> int:
        return sum(h.added for h in self.hunks)

    @property
    def removed(self) -> int:
        return sum(h.removed for h in self.hunks)


class Diff(BaseModel):
    """A parsed pull-request diff: the change set between `base_ref` and `head_ref`,
    materialized relative to their merge-base (`base_commit`)."""

    base_ref: str
    head_ref: str
    base_commit: str  # the merge-base commit SHA we materialize on top of
    head_commit: str
    files: list[FileChange] = Field(default_factory=list)

    def all_hunks(self) -> list[Hunk]:
        return [h for f in self.files for h in f.hunks]

    def hunk_by_id(self) -> dict[str, Hunk]:
        return {h.id: h for h in self.all_hunks()}

    def atomic_files(self) -> list[FileChange]:
        return [f for f in self.files if f.is_atomic]

    @property
    def total_lines(self) -> int:
        return sum(f.added + f.removed for f in self.files)

    @property
    def total_files(self) -> int:
        return len(self.files)


class Slice(BaseModel):
    """One reviewable sub-PR: an ordered group of hunks (and/or atomic files) with a
    single intent and explicit dependencies on earlier slices."""

    order: int  # 1-based position in the stack
    title: str
    intent: str = ""
    hunk_ids: list[str] = Field(default_factory=list)
    atomic_paths: list[str] = Field(default_factory=list)
    depends_on: list[int] = Field(default_factory=list)

    # Filled in after materialization / validation:
    commit_sha: str | None = None
    line_count: int = 0
    file_count: int = 0


class SlicePlan(BaseModel):
    """A candidate decomposition of a `Diff` into an ordered stack of slices."""

    strategy: str
    slices: list[Slice] = Field(default_factory=list)
    candidate_index: int = 0
    notes: list[str] = Field(default_factory=list)

    def assigned_hunk_ids(self) -> list[str]:
        return [hid for s in self.slices for hid in s.hunk_ids]

    def assigned_atomic_paths(self) -> list[str]:
        return [p for s in self.slices for p in s.atomic_paths]
