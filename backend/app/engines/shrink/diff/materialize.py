"""Materialize a `SlicePlan` into a chain of git commits and verify completeness.

For each level k = 1..n we build the tree for `base + slice_1 + ... + slice_k` **fresh
from the merge-base**: read-tree the base into a temp index, `git apply --cached` a
cumulative patch of all *text* hunks in slices 1..k (their `@@` line numbers reference the
base), reconcile *atomic* files (binary/rename/mode) against head, write-tree -> tree_k.
Building each level fresh from the base sidesteps line-offset drift entirely. Applying all
hunks reproduces head, so completeness holds by construction; `verify_completeness` is the
exact safety net.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from .completeness import CompletenessResult, verify_completeness
from .gitio import Git
from .models import Diff, FileChange, SlicePlan


class PartitionError(RuntimeError):
    """The slice plan is not a valid partition of the diff. Raising this *before*
    materializing is what guarantees the completeness invariant can hold."""


class SliceCommit(BaseModel):
    order: int
    title: str
    intent: str = ""
    commit_sha: str
    branch: str | None = None
    base_branch: str | None = None
    added: int = 0
    removed: int = 0
    files: int = 0
    depends_on: list[int] = []


class MaterializeResult(BaseModel):
    base_commit: str
    head_commit: str
    final_commit: str
    slices: list[SliceCommit]
    completeness: CompletenessResult
    refs_written: bool = False


def slugify(text: str, max_len: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len].strip("-") or "change"


def validate_partition(diff: Diff, plan: SlicePlan) -> None:
    """Assert every hunk and every atomic file is assigned to exactly one slice."""
    all_hunks = {h.id for h in diff.all_hunks()}
    assigned = plan.assigned_hunk_ids()
    if len(assigned) != len(set(assigned)):
        dupes = {x for x in assigned if assigned.count(x) > 1}
        raise PartitionError(f"hunk(s) assigned to multiple slices: {sorted(dupes)}")
    if set(assigned) != all_hunks:
        missing = all_hunks - set(assigned)
        extra = set(assigned) - all_hunks
        raise PartitionError(f"hunk coverage mismatch (missing={sorted(missing)}, unknown={sorted(extra)})")

    all_atomic = {f.path for f in diff.atomic_files()}
    assigned_atomic = plan.assigned_atomic_paths()
    if len(assigned_atomic) != len(set(assigned_atomic)):
        raise PartitionError("atomic file assigned to multiple slices")
    if set(assigned_atomic) != all_atomic:
        raise PartitionError(
            f"atomic-file coverage mismatch (missing={sorted(all_atomic - set(assigned_atomic))}, "
            f"unknown={sorted(set(assigned_atomic) - all_atomic)})"
        )


def slice_patch_text(diff: Diff, hunk_ids: list[str]) -> str:
    """Public helper: the patch text for exactly the given hunks (for display/labeling)."""
    return _cumulative_patch(diff, set(hunk_ids))


def _cumulative_patch(diff: Diff, hunk_ids: set[str]) -> str:
    """Patch text for all included *text* hunks, grouped by file (diff order), hunks
    sorted by source line so git applies them in order."""
    out: list[str] = []
    for f in diff.files:
        if f.is_atomic:
            continue
        included = [h for h in f.hunks if h.id in hunk_ids]
        if not included:
            continue
        included.sort(key=lambda h: h.source_start)
        out.append(f.header_text)
        out.extend(h.text for h in included)
    return "".join(out)


def _reconcile_atomic(git: Git, index_file: str, head_tree: str, files: list[FileChange]) -> None:
    """Make the index entry for each atomic file match head (binary/rename/mode/delete)."""
    for f in files:
        head_entry = git.ls_tree_entry(head_tree, f.path)
        if head_entry is not None:
            mode, sha = head_entry
            git.update_index_cacheinfo(index_file, mode, sha, f.path)
        else:
            git.update_index_remove(index_file, f.path)  # deleted in head
        if f.old_path and f.old_path != f.path:
            git.update_index_remove(index_file, f.old_path)  # renamed away


def materialize(
    repo: str,
    diff: Diff,
    plan: SlicePlan,
    *,
    out_prefix: str = "shrink/",
    write_refs: bool = False,
) -> MaterializeResult:
    validate_partition(diff, plan)
    git = Git(repo)
    base_tree = git.tree_of(diff.base_commit)
    head_tree = git.tree_of(diff.head_commit)
    hunks_by_file_atomic = {f.path: f for f in diff.atomic_files()}

    parent = diff.base_commit
    cum_hunk_ids: set[str] = set()
    cum_atomic: list[FileChange] = []
    commits: list[SliceCommit] = []
    prev_branch: str | None = diff.base_ref

    for s in plan.slices:
        cum_hunk_ids |= set(s.hunk_ids)
        cum_atomic += [hunks_by_file_atomic[p] for p in s.atomic_paths if p in hunks_by_file_atomic]

        with git.temp_index() as idx:
            git.read_tree(idx, base_tree)
            patch = _cumulative_patch(diff, cum_hunk_ids)
            if patch:
                git.apply_cached(idx, patch)
            _reconcile_atomic(git, idx, head_tree, cum_atomic)
            tree_k = git.write_tree(idx)

        message = s.title if not s.intent else f"{s.title}\n\n{s.intent}"
        commit_k = git.commit_tree(tree_k, message, parent)
        parent = commit_k

        branch = f"{out_prefix}{s.order}-{slugify(s.title)}" if write_refs else None
        commits.append(
            SliceCommit(
                order=s.order,
                title=s.title,
                intent=s.intent,
                commit_sha=commit_k,
                branch=branch,
                base_branch=prev_branch,
                added=sum(h.added for h in diff.all_hunks() if h.id in set(s.hunk_ids)),
                removed=sum(h.removed for h in diff.all_hunks() if h.id in set(s.hunk_ids)),
                files=len({h.file_path for h in diff.all_hunks() if h.id in set(s.hunk_ids)})
                + len(s.atomic_paths),
                depends_on=s.depends_on,
            )
        )
        if write_refs and branch:
            git.update_ref(f"refs/heads/{branch}", commit_k)
            prev_branch = branch

    final_commit = parent
    completeness = verify_completeness(git, final_commit, diff.head_commit)

    return MaterializeResult(
        base_commit=diff.base_commit,
        head_commit=diff.head_commit,
        final_commit=final_commit,
        slices=commits,
        completeness=completeness,
        refs_written=write_refs,
    )
