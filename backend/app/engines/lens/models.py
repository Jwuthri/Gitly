"""Pydantic v2 models — the lens cluster contract.

These models ARE the contract for `POST /lens/analyze`. Each object sets
`extra="forbid"` and makes required fields non-default, so the engine never emits an
extra field or omits a required one. Ported from pr-visual-diff (`app/models.py`).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Confidence(str, Enum):
    """high = structural fingerprint match; medium = template match; low = stub/heuristic."""

    high = "high"
    medium = "medium"
    low = "low"


class ClusterKind(str, Enum):
    rename = "rename"
    signature_change = "signature_change"
    import_migration = "import_migration"
    api_replacement = "api_replacement"
    type_change = "type_change"
    boilerplate_insertion = "boilerplate_insertion"
    conditional_removal = "conditional_removal"
    new_file = "new_file"
    deleted_file = "deleted_file"
    file_rewrite = "file_rewrite"
    generated_file = "generated_file"
    other = "other"
    ungrouped = "ungrouped"


class FileStatus(str, Enum):
    added = "added"
    modified = "modified"
    deleted = "deleted"
    renamed = "renamed"
    copied = "copied"


class SourceType(str, Enum):
    raw_diff = "raw_diff"
    pr_url = "pr_url"
    diff_url = "diff_url"


class DiffLineType(str, Enum):
    context = "context"
    add = "add"
    remove = "remove"


class Source(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: SourceType
    ref: str | None = Field(default=None, description="Original PR/diff URL when type != raw_diff.")
    repo: str | None = Field(default=None, description="owner/name, when known.")
    head_sha: str | None = None


class Stats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    files_changed: int = Field(ge=0)
    lines_added: int = Field(ge=0)
    lines_removed: int = Field(ge=0)
    hunk_count: int = Field(ge=0)
    cluster_count: int = Field(ge=0)


class FileChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="Post-image path (new path for renames).")
    old_path: str | None = Field(default=None, description="Pre-image path; set for renames/copies/deletes.")
    status: FileStatus
    language: str | None = Field(default=None, description="Detected language id, e.g. 'typescript'.")
    is_generated: bool = False
    is_binary: bool = False
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    hunk_ids: list[str] = Field(default_factory=list)


class DiffLine(BaseModel):
    """A single line inside a hunk. `content` has no leading +/-/space marker and no trailing newline."""

    model_config = ConfigDict(extra="forbid")

    type: DiffLineType
    content: str
    old_no: int | None = None
    new_no: int | None = None


class Hunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    file: str = Field(description="Post-image file path this hunk belongs to.")
    old_file: str | None = None
    header: str | None = Field(default=None, description="Text after '@@ ... @@', if any.")
    language: str | None = None
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[DiffLine] = Field(default_factory=list)


class Site(BaseModel):
    """One occurrence of a cluster's pattern."""

    model_config = ConfigDict(extra="forbid")

    hunk_id: str
    file: str
    line: int = Field(description="Anchor line in the post-image (usually the hunk's new_start).")
    label: str = Field(description="Display label, e.g. 'src/api/users.ts:42'.")
    binding: dict[str, str] | None = Field(default=None, description="Template-hole / substitution bindings.")


class Outlier(BaseModel):
    """A site that almost-but-not-quite matches the cluster pattern."""

    model_config = ConfigDict(extra="forbid")

    hunk_id: str
    reason: str
    expected: str | None = None
    found: str | None = None


class Cluster(BaseModel):
    """A conceptual change. `representative_hunk_id` is one of `sites[].hunk_id`;
    `site_count == len(sites)`; `file_count` == distinct files across sites."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: ClusterKind
    title: str
    description: str | None = None
    confidence: Confidence
    confidence_reason: str
    representative_hunk_id: str
    sites: list[Site] = Field(default_factory=list)
    site_count: int = Field(ge=1)
    file_count: int = Field(ge=1)
    outliers: list[Outlier] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    """Canonical engine output. Every hunk id in `hunks` is referenced by exactly one
    cluster (via `sites[].hunk_id`); every site references a hunk that exists."""

    model_config = ConfigDict(extra="forbid")

    id: str
    engine_version: str
    source: Source
    title: str | None = None
    stats: Stats
    files: list[FileChange] = Field(default_factory=list)
    hunks: dict[str, Hunk] = Field(default_factory=dict)
    clusters: list[Cluster] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
