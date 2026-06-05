"""Ship a verified shrink stack as **chained stacked PRs** on GitHub.

The engine already materialized each slice as a branch carrying its `base_branch` (slice N
stacks on slice N-1; slice 1 on the original base). So shipping is: push the branches, then
open one PR per slice with `head=branch, base=base_branch`. Uses the dev's own `git` + `gh`
auth — no GitHub App required. Falls back to compare URLs if `gh` can't open a PR."""
from __future__ import annotations

import subprocess

from backend.app.engines.shrink.service import ShrinkResult


def pr_specs(result: ShrinkResult) -> list[dict]:
    """Ordered {branch, base, title, body} per materialized slice (pure — no side effects)."""
    mat = result.materialized
    if not mat:
        return []
    specs: list[dict] = []
    for s in mat.slices:
        if not s.branch:
            continue
        base = s.base_branch or result.base_ref
        body = (s.intent or "").strip()
        body += f"\n\n— slice {s.order} of a gitly stack · base `{base}` · "
        body += "verified `tree(base+slices) == tree(head)` ✅"
        specs.append({"branch": s.branch, "base": base, "title": s.title, "body": body})
    return specs


def _git(repo: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, check=check)


def push_branches(repo: str, branches: list[str], *, remote: str = "origin") -> None:
    """Push the slice branches (force-with-lease, since a re-shrink rewrites them)."""
    if branches:
        _git(repo, "push", "--force-with-lease", remote, *branches)


def open_pr(repo: str, spec: dict) -> tuple[bool, str]:
    """Open one PR via `gh`. Returns (ok, url-or-error-line)."""
    r = subprocess.run(
        ["gh", "pr", "create", "--base", spec["base"], "--head", spec["branch"],
         "--title", spec["title"], "--body", spec["body"]],
        cwd=repo, capture_output=True, text=True,
    )
    lines = [ln for ln in (r.stdout + "\n" + r.stderr).splitlines() if ln.strip()]
    return r.returncode == 0, (lines[-1] if lines else "")


def remote_slug(repo: str) -> str | None:
    """`owner/repo` from the origin remote, for compare URLs."""
    try:
        url = _git(repo, "remote", "get-url", "origin").stdout.strip()
    except subprocess.CalledProcessError:
        return None
    if url.startswith("git@"):
        url = url.split(":", 1)[-1]
    elif "github.com/" in url:
        url = url.split("github.com/", 1)[-1]
    return url[:-4] if url.endswith(".git") else url


def compare_url(slug: str, base: str, head: str) -> str:
    return f"https://github.com/{slug}/compare/{base}...{head}?expand=1"
