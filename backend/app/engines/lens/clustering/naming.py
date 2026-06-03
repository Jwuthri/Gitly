"""Honest, template-derived cluster titles — deterministic labels from path/status/anchor,
no model in the loop. Intentionally modest so a title never over-claims intent."""
from __future__ import annotations

from ..diff.parser import ParsedFile, ParsedHunk
from ..models import FileStatus


def _first_changed_line(hunk: ParsedHunk) -> int:
    for line in hunk.lines:
        if line.new_no is not None:
            return line.new_no
    return hunk.new_start


def anchor_line(hunk: ParsedHunk) -> int:
    """The site anchor line in the post-image for `hunk`."""
    return _first_changed_line(hunk)


def title_for_hunk(file: ParsedFile, hunk: ParsedHunk) -> str:
    if file.status == FileStatus.added:
        return f"New file {file.path}"
    if file.status == FileStatus.deleted:
        return f"Deleted file {file.path}"
    if file.status in (FileStatus.renamed, FileStatus.copied) and file.old_path:
        verb = "Renamed" if file.status == FileStatus.renamed else "Copied"
        return f"{verb} {file.old_path} -> {file.path}"
    return f"Edit in {file.path}:{anchor_line(hunk)}"


def label_for_site(file: ParsedFile, hunk: ParsedHunk) -> str:
    """Display label for a site, e.g. ``src/api/users.ts:42``."""
    return f"{file.path}:{anchor_line(hunk)}"
