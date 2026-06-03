"""gitly CLI — `gitly trace`, `gitly scan`, plus seams for `shrink` / `lens`."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer

from backend.app.engines.trace.blame import summarize, trace_file
from backend.app.security.secret_firewall import scan as secret_scan

app = typer.Typer(help="gitly — git-quality tooling for the AI-authorship era.", no_args_is_help=True)
trace_app = typer.Typer(help="AI authorship provenance.")
app.add_typer(trace_app, name="trace")


def _repo_root() -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
        )
        return Path(out.stdout.strip())
    except Exception:
        return Path.cwd()


def _tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True)
    return out.stdout.splitlines()


def _tag(ln) -> str:
    if ln.author_type.value == "human":
        return "human"
    badge = ln.model or ln.agent.value
    mark = "~" if ln.inferred else ""           # ~ = inferred, not recorded
    rev = "" if ln.reviewed else " !unreviewed"
    return f"AI:{badge}{mark}{rev}"


def _render_summary(s) -> str:
    pct = (100 * s.ai_lines / s.total_lines) if s.total_lines else 0
    rows = [
        f"repo: {s.repo}",
        f"lines: {s.total_lines}   ai: {s.ai_lines} ({pct:.0f}%)   human: {s.human_lines}   hybrid: {s.hybrid_lines}",
        f"unreviewed AI lines: {s.unreviewed_ai_lines}",
    ]
    if s.by_model:
        rows.append("by model: " + ", ".join(f"{k}={v}" for k, v in s.by_model.items()))
    return "\n".join(rows)


@trace_app.callback(invoke_without_command=True)
def trace_default(
    ctx: typer.Context,
    file: str = typer.Argument(None, help="File to trace (blame-style provenance)."),
    summary: bool = typer.Option(False, "--summary", help="Repo rollup instead of per-line."),
):
    if ctx.invoked_subcommand is not None:
        return
    root = _repo_root()
    if summary or not file:
        files = [file] if file else _tracked_files(root)
        all_lines = []
        for f in files:
            try:
                all_lines += trace_file(root, f)
            except Exception:
                continue
        typer.echo(_render_summary(summarize(all_lines, repo=root.name)))
        return
    for ln in trace_file(root, file):
        typer.echo(f"{ln.line_no:>5}  {_tag(ln):<26} {ln.content}")


@app.command()
def scan(staged: bool = typer.Option(False, "--staged", help="Scan staged changes (for a pre-commit hook).")):
    """Secret firewall: block secrets before they're committed."""
    root = _repo_root()
    if staged:
        text = subprocess.run(
            ["git", "-C", str(root), "diff", "--cached"], capture_output=True, text=True
        ).stdout
    else:
        text = sys.stdin.read()
    findings = secret_scan(text)
    if findings:
        for f in findings:
            typer.secho(f"  secret[{f.kind}] line {f.line_no}: {f.match[:12]}…", fg="red")
        typer.secho(f"x {len(findings)} potential secret(s) — commit blocked.", fg="red", err=True)
        raise typer.Exit(1)
    typer.secho("ok: no secrets detected", fg="green")


@app.command()
def shrink(
    base: str = typer.Argument(..., help="Base ref (e.g. main)"),
    head: str = typer.Argument("HEAD", help="Head ref"),
    repo: str = typer.Option(".", "--repo", help="Path to the git repo"),
    strength: str = typer.Option("balanced", "--strength", help="gentle | balanced | aggressive"),
    max_lines: int = typer.Option(0, "--max-lines", help="Override max lines/slice (0 = use --strength)"),
    write_refs: bool = typer.Option(False, "--write-refs", help="Create shrink/* branches for each slice"),
    llm: bool = typer.Option(False, "--llm", help="Use the LLM labeler (needs GITLY_ANTHROPIC_API_KEY)"),
):
    """Split a PR (base..head) into a verified stack of small sub-PRs."""
    from backend.app.engines.shrink.planner.planner import PlanOptions
    from backend.app.engines.shrink.service import shrink as run_shrink

    presets = {
        "gentle": dict(max_lines=1500, min_lines=300, max_slices=2),
        "balanced": dict(max_lines=400, min_lines=40, max_slices=6),
        "aggressive": dict(max_lines=120, min_lines=1, max_slices=20),
    }
    preset = dict(presets.get(strength, presets["balanced"]))
    if max_lines:
        preset["max_lines"] = max_lines
    root = repo if repo != "." else str(_repo_root())
    res = run_shrink(root, base, head, opts=PlanOptions(**preset), write_refs=write_refs, prefer_llm=llm)
    typer.echo(f"{res.original_lines} lines / {res.original_files} files  ->  {len(res.slices)} slices")
    for s in res.slices:
        dep = f"  (after #{', #'.join(map(str, s.depends_on))})" if s.depends_on else ""
        typer.echo(f"  #{s.order}  {s.title}  [{s.lines} ln / {s.files} files]{dep}")
        if s.intent:
            typer.echo(f"        {s.intent}")
    if res.completeness_ok:
        typer.secho("ok: completeness verified — tree(base + slices) == tree(head)", fg="green")
    else:
        typer.secho("x: completeness FAILED — stack not shipped", fg="red", err=True)
        raise typer.Exit(1)
    if write_refs and res.materialized:
        typer.echo("branches:")
        for sc in res.materialized.slices:
            typer.echo(f"  {sc.branch}  ({sc.commit_sha[:10]})")


@app.command()
def lens(file: str = typer.Argument(..., help="Path to a unified .diff file")):
    """Cluster a diff into conceptual change cards. (engine ports from pr-visual-diff)"""
    typer.echo("lens: engine port pending — see MIGRATION.md (../pr-visual-diff)")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
