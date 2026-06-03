"""Parse a PR diff (base..head) into the engine's structured `Diff` model.

We compute the diff relative to the **merge-base** of base and head (equivalent to
GitHub's 3-dot PR diff), and materialize on top of that merge-base — so applying the full
diff reproduces head exactly, which is what makes the completeness invariant hold by
construction.
"""
from __future__ import annotations

from unidiff import PatchSet

from .gitio import Git
from .models import ChangeType, Diff, FileChange, Hunk


def _strip_prefix(p: str) -> str | None:
    if p == "/dev/null":
        return None
    if len(p) > 2 and p[1] == "/" and p[0] in "ab":
        return p[2:]
    return p


def _classify(pf) -> ChangeType:
    if pf.is_binary_file:
        return ChangeType.BINARY
    if pf.is_added_file:
        return ChangeType.ADD
    if pf.is_removed_file:
        return ChangeType.DELETE
    if pf.is_rename:
        return ChangeType.RENAME
    if len(pf) == 0:  # no hunks, not binary/rename/add/remove -> mode-only
        return ChangeType.MODE
    return ChangeType.MODIFY


def _file_header(pf, has_hunks: bool) -> str:
    parts: list[str] = []
    if pf.patch_info:
        parts.append(str(pf.patch_info))
    if has_hunks:
        parts.append(f"--- {pf.source_file}\n")
        parts.append(f"+++ {pf.target_file}\n")
    return "".join(parts)


def parse_patch_text(text: str, base_ref: str, head_ref: str, base_commit: str, head_commit: str) -> Diff:
    """Parse a raw unified diff string into a `Diff`. Pure; no git calls."""
    patch_set = PatchSet(text)
    files: list[FileChange] = []
    for pf in patch_set:
        change_type = _classify(pf)
        new_path = _strip_prefix(pf.target_file) or _strip_prefix(pf.source_file)
        old_path = _strip_prefix(pf.source_file)
        assert new_path is not None, f"could not determine path for {pf!r}"

        hunks: list[Hunk] = []
        for i, h in enumerate(pf):
            hunks.append(
                Hunk(
                    file_path=new_path,
                    hunk_index=i,
                    source_start=h.source_start,
                    source_length=h.source_length,
                    target_start=h.target_start,
                    target_length=h.target_length,
                    added=h.added,
                    removed=h.removed,
                    text=str(h),
                )
            )
        files.append(
            FileChange(
                path=new_path,
                old_path=old_path if old_path != new_path else None,
                change_type=change_type,
                header_text=_file_header(pf, has_hunks=bool(hunks)),
                hunks=hunks,
            )
        )
    return Diff(
        base_ref=base_ref,
        head_ref=head_ref,
        base_commit=base_commit,
        head_commit=head_commit,
        files=files,
    )


def parse_pr(repo: str, base_ref: str, head_ref: str) -> Diff:
    """Fetch and parse the diff for a PR-like base/head pair from a real repo."""
    git = Git(repo)
    base_commit = git.rev_parse(base_ref)
    head_commit = git.rev_parse(head_ref)
    merge_base = git.merge_base(base_commit, head_commit)
    raw = git.raw_diff(merge_base, head_commit)
    return parse_patch_text(
        raw,
        base_ref=base_ref,
        head_ref=head_ref,
        base_commit=merge_base,  # materialize on the merge-base
        head_commit=head_commit,
    )
