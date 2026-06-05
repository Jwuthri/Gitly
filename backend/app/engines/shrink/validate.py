"""Validate a shrink stack: run a build/test command against EACH slice in isolation, proving
the stack isn't just tree-equal to head but that **every slice on its own is green**.

Each materialized slice commit is the cumulative tree (base + slices 1..k), so we check it out
into a throwaway **git worktree** and run the check there — optionally inside a **Docker**
container for real environment isolation. A red slice means the (heuristic) dependency ordering
shipped something too late; the stack shouldn't be opened as PRs until it's fixed."""
from __future__ import annotations

import shutil
import subprocess
import tempfile

from pydantic import BaseModel

from backend.app.engines.shrink.service import ShrinkResult


class SliceCheck(BaseModel):
    order: int
    title: str
    ok: bool
    returncode: int
    output: str = ""        # tail of stdout+stderr, for red slices


def _run(cmd: list[str], *, cwd: str | None = None, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def validate_stack(
    repo: str,
    result: ShrinkResult,
    check_cmd: str,
    *,
    docker_image: str | None = None,
    timeout: int = 600,
) -> list[SliceCheck]:
    """Run `check_cmd` against each materialized slice's cumulative tree. Returns one
    `SliceCheck` per slice (in stack order). Requires materialized slice commits."""
    mat = result.materialized
    if not mat:
        return []
    checks: list[SliceCheck] = []
    for s in mat.slices:
        wt = tempfile.mkdtemp(prefix=f"gitly-slice-{s.order}-")
        try:
            _run(["git", "-C", repo, "worktree", "add", "--detach", wt, s.commit_sha])
            if docker_image:
                proc = _run(
                    ["docker", "run", "--rm", "-v", f"{wt}:/work", "-w", "/work",
                     docker_image, "sh", "-c", check_cmd],
                    timeout=timeout,
                )
            else:
                proc = _run(["sh", "-c", check_cmd], cwd=wt, timeout=timeout)
            tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-8:])
            checks.append(SliceCheck(
                order=s.order, title=s.title, ok=proc.returncode == 0,
                returncode=proc.returncode, output=tail,
            ))
        finally:
            _run(["git", "-C", repo, "worktree", "remove", "--force", wt])
            shutil.rmtree(wt, ignore_errors=True)
    return checks
