"""The diff-completeness invariant:

    tree(base + slice_1 + ... + slice_n) == tree(head)

We verify this *exactly* by comparing git tree-object IDs — not diff text. Tree-ID
equality is byte-for-byte at the content level, which sidesteps whitespace / EOL /
diff-text drift entirely. If the trees differ, the shrink is aborted. Non-negotiable.
"""
from __future__ import annotations

from pydantic import BaseModel

from .gitio import Git


class CompletenessResult(BaseModel):
    ok: bool
    final_tree: str
    head_tree: str
    divergence: str = ""

    def raise_if_failed(self) -> None:
        if not self.ok:
            raise CompletenessError(self)


class CompletenessError(RuntimeError):
    def __init__(self, result: CompletenessResult):
        self.result = result
        super().__init__(
            "Completeness invariant violated: the materialized stack does not reproduce "
            f"head.\n  produced tree: {result.final_tree}\n      head tree: {result.head_tree}\n"
            f"  divergence:\n{result.divergence}"
        )


def verify_completeness(git: Git, final_commit: str, head_commit: str) -> CompletenessResult:
    final_tree = git.tree_of(final_commit)
    head_tree = git.tree_of(head_commit)
    if final_tree == head_tree:
        return CompletenessResult(ok=True, final_tree=final_tree, head_tree=head_tree)
    divergence = git.diff_tree(final_tree, head_tree)
    return CompletenessResult(ok=False, final_tree=final_tree, head_tree=head_tree, divergence=divergence)
