"""A thin wrapper over the real `git` CLI.

We drive `git` directly (not a binding) because correctness depends on matching git's
exact apply/tree semantics. The materializer uses git's *plumbing* (read-tree /
apply --cached / write-tree / commit-tree) against a temporary index so it never disturbs
the user's working tree or index.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class GitError(RuntimeError):
    def __init__(self, args: list[str], returncode: int, stderr: str):
        self.args_ = args
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"git {' '.join(args)} failed ({returncode}): {stderr.strip()}")


class Git:
    """Operations scoped to a single repository working directory."""

    def __init__(self, repo: str | Path):
        self.repo = Path(repo).resolve()
        if not (self.repo / ".git").exists() and not (self.repo / "HEAD").exists():
            pass

    def run(
        self,
        *args: str,
        input_bytes: bytes | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> str:
        full_env = {**os.environ, **(env or {})}
        proc = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            input=input_bytes,
            capture_output=True,
            env=full_env,
            timeout=120,   # materialize can chew on big repos, but never hang forever
        )
        if check and proc.returncode != 0:
            raise GitError(list(args), proc.returncode, proc.stderr.decode("utf-8", "replace"))
        return proc.stdout.decode("utf-8", "replace")

    def run_bytes(self, *args: str, check: bool = True) -> bytes:
        proc = subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, timeout=120)
        if check and proc.returncode != 0:
            raise GitError(list(args), proc.returncode, proc.stderr.decode("utf-8", "replace"))
        return proc.stdout

    # --- read operations -------------------------------------------------

    def rev_parse(self, ref: str) -> str:
        return self.run("rev-parse", "--verify", ref).strip()

    def tree_of(self, commit: str) -> str:
        return self.run("rev-parse", "--verify", f"{commit}^{{tree}}").strip()

    def merge_base(self, a: str, b: str) -> str:
        return self.run("merge-base", a, b).strip()

    def raw_diff(self, base: str, head: str) -> str:
        """Unified diff base..head, with binary payloads and rename detection."""
        return self.run(
            "diff",
            "--no-color",
            "--binary",
            "--find-renames",
            "--find-copies",
            "--no-ext-diff",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            f"{base}",
            f"{head}",
        )

    def ls_tree_entry(self, tree: str, path: str) -> tuple[str, str] | None:
        """Return (mode, blob_sha) for `path` in `tree`, or None if absent."""
        out = self.run("ls-tree", tree, "--", path).strip()
        if not out:
            return None
        meta, _, _ = out.partition("\t")
        mode, _type, sha = meta.split()
        return mode, sha

    def diff_tree(self, tree_a: str, tree_b: str) -> str:
        return self.run("diff", "--no-color", f"{tree_a}", f"{tree_b}")

    # --- temp-index plumbing (never touches the user's index/worktree) ---

    @contextmanager
    def temp_index(self) -> Iterator[str]:
        fd, path = tempfile.mkstemp(prefix="shrink-index-")
        os.close(fd)
        os.unlink(path)  # git wants to create it itself
        try:
            yield path
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def read_tree(self, index_file: str, tree: str) -> None:
        self.run("read-tree", tree, env={"GIT_INDEX_FILE": index_file})

    def apply_cached(self, index_file: str, patch: str) -> None:
        self.run(
            "apply",
            "--cached",
            "--whitespace=nowarn",
            input_bytes=patch.encode("utf-8"),
            env={"GIT_INDEX_FILE": index_file},
        )

    def apply_check(self, index_file: str, patch: str) -> bool:
        try:
            self.run(
                "apply",
                "--cached",
                "--check",
                "--whitespace=nowarn",
                input_bytes=patch.encode("utf-8"),
                env={"GIT_INDEX_FILE": index_file},
            )
            return True
        except GitError:
            return False

    def update_index_cacheinfo(self, index_file: str, mode: str, sha: str, path: str) -> None:
        self.run(
            "update-index",
            "--add",
            "--cacheinfo",
            f"{mode},{sha},{path}",
            env={"GIT_INDEX_FILE": index_file},
        )

    def update_index_remove(self, index_file: str, path: str) -> None:
        self.run("update-index", "--force-remove", path, env={"GIT_INDEX_FILE": index_file})

    def write_tree(self, index_file: str) -> str:
        return self.run("write-tree", env={"GIT_INDEX_FILE": index_file}).strip()

    def commit_tree(self, tree: str, message: str, parent: str | None) -> str:
        args = ["commit-tree", tree, "-m", message]
        if parent:
            args += ["-p", parent]
        env = {
            "GIT_AUTHOR_NAME": "gitly shrink",
            "GIT_AUTHOR_EMAIL": "shrink@local",
            "GIT_COMMITTER_NAME": "gitly shrink",
            "GIT_COMMITTER_EMAIL": "shrink@local",
            # Deterministic timestamps so identical inputs produce identical commits.
            "GIT_AUTHOR_DATE": "2000-01-01T00:00:00 +0000",
            "GIT_COMMITTER_DATE": "2000-01-01T00:00:00 +0000",
        }
        return self.run(*args, env=env).strip()

    def update_ref(self, ref: str, commit: str) -> None:
        self.run("update-ref", ref, commit)

    # --- worktrees (used by the local validator) -------------------------

    def add_worktree(self, path: str, commit: str) -> None:
        self.run("worktree", "add", "--detach", "-f", path, commit)

    def remove_worktree(self, path: str) -> None:
        self.run("worktree", "remove", "--force", path, check=False)
