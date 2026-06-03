"""gitly CLI — `gitly trace`, `gitly scan`, plus seams for `shrink` / `lens`."""
from __future__ import annotations

import os
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


@app.command()
def commit(
    message: str = typer.Argument(None, help="Commit message (omit to auto-generate from the diff)"),
    all: bool = typer.Option(False, "--all", "-a", help="Stage all changes, including untracked files"),
    path: list[str] = typer.Option(None, "--path", help="Stage only these path(s) (repeatable)"),
    split: bool = typer.Option(False, "--split", help="Auto-split the working tree into several logical commits"),
    llm: bool = typer.Option(False, "--llm", help="Force the LLM to write the message(s)"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Never call an LLM — use the offline heuristic"),
    repo: str = typer.Option(".", "--repo", help="Path to the git repo"),
):
    """Commit cleanly: stage safe files, block on secrets, refuse on a protected branch.

    Omit the message and gitly writes a conventional one from the diff — via your
    configured brain (see `gitly auth`) or, with none, an offline heuristic. Use
    --split to break a big working tree into several independently-reviewable commits.

    The safe-add guard never stages .env / keys / build junk; pass them with --path
    only if you truly mean to."""
    from backend.app.engines.copilot.ops import GitError, safe_commit, split_commit

    cwd = repo if repo != "." else str(_repo_root())
    mode = "off" if no_llm else "llm" if llm else "auto"

    try:
        if split:
            ok, lines = split_commit(cwd, stage_all=all, msg_mode=mode)
            typer.secho("Split into commits:" if ok else "Could not split:", fg="green" if ok else "red", err=not ok)
            for ln in lines:
                typer.echo(ln)
            raise typer.Exit(0 if ok else 1)
        ok, msg = safe_commit(cwd, message, stage_all=all, paths=path, msg_mode=mode)
    except GitError as e:
        typer.secho(f"git error: {e}", fg="red", err=True)
        raise typer.Exit(1)
    typer.secho(msg, fg="green" if ok else "red", err=not ok)
    raise typer.Exit(0 if ok else 1)


@app.command()
def absorb(
    into: str = typer.Option(None, "--into", help="Commit ref to absorb every change into"),
    repo: str = typer.Option(".", "--repo", help="Path to the git repo"),
):
    """Fold uncommitted changes into the commit(s) they belong to and re-stack."""
    from backend.app.engines.copilot.ops import GitError
    from backend.app.engines.copilot.ops import absorb as run_absorb

    try:
        ok, msg = run_absorb(repo if repo != "." else str(_repo_root()), into)
    except GitError as e:
        typer.secho(f"git error: {e}", fg="red", err=True)
        raise typer.Exit(1)
    typer.secho(msg, fg="green" if ok else "red", err=not ok)
    raise typer.Exit(0 if ok else 1)


def _show_brain(brain) -> None:
    cfg = brain.load_config()
    active = brain.provider()  # also loads the nearest .env
    sources: list[str] = []
    if os.environ.get("OPENAI_API_KEY"):
        sources.append("OPENAI_API_KEY (env/.env)")
    if cfg.get("openai_key"):
        sources.append("openai_key (config)")
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GITLY_ANTHROPIC_API_KEY"):
        sources.append("ANTHROPIC_API_KEY (env)")
    if cfg.get("anthropic_key"):
        sources.append("anthropic_key (config)")
    typer.echo(f"active provider : {active}")
    typer.echo(f"claude code     : {'available' if brain.has_claude_code() else 'not found'}")
    typer.echo(f"api keys        : {', '.join(sources) if sources else 'none'} (never displayed, never committed)")
    exists = brain.CONFIG_PATH.exists()
    typer.echo(f"config file     : {brain.CONFIG_PATH}{'' if exists else ' (not created yet)'}")


@app.command()
def auth(
    provider: str = typer.Option(None, "--provider", help="claude-code | openai | anthropic | heuristic"),
    key: str = typer.Option(None, "--key", help="API key for openai/anthropic (omit to be prompted securely)"),
    show: bool = typer.Option(False, "--show", help="Just show the active brain and exit"),
):
    """Set up the gitly 'brain' once — used for commit messages & semantic splitting.

    Zero-config if Claude Code is installed (no key needed). Otherwise drop in an
    OpenAI/Anthropic key — stored at ~/.config/gitly/config.json (chmod 600), or just
    leave it in your project's .env. Keys go ONLY to that provider, and every diff is
    secret-redacted before it's sent."""
    from backend.app.engines.copilot import brain

    brain._load_dotenv()  # so a key already sitting in the project's .env is detected below

    if show:
        _show_brain(brain)
        return

    if not provider:
        has_cc = brain.has_claude_code()
        typer.echo("gitly brain — how should I write commit messages & splits?\n")
        typer.echo(f"  1. claude-code   {'(detected)' if has_cc else '(not found)'}  — zero-config, uses your Claude Code CLI")
        typer.echo("  2. openai        — needs an API key (sk-…)")
        typer.echo("  3. anthropic     — needs an API key (sk-ant-…)")
        typer.echo("  4. heuristic     — fully offline, no LLM\n")
        choice = typer.prompt("Choose [1-4]", default="1" if has_cc else "2").strip().lower()
        provider = {"1": "claude-code", "2": "openai", "3": "anthropic", "4": "heuristic"}.get(choice, choice)

    if provider not in {"claude-code", "openai", "anthropic", "heuristic"}:
        typer.secho(f"Unknown provider '{provider}'.", fg="red", err=True)
        raise typer.Exit(1)

    cfg = brain.load_config()
    cfg["provider"] = provider

    if provider in {"openai", "anthropic"}:
        env_name = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
        if not key and os.environ.get(env_name):
            typer.secho(f"Found {env_name} in your environment/.env — using that, nothing stored.", fg="green")
        else:
            if not key:
                key = typer.prompt(f"{provider} API key", hide_input=True)
            cfg["openai_key" if provider == "openai" else "anthropic_key"] = key.strip()
    elif provider == "claude-code" and not brain.has_claude_code():
        typer.secho("! 'claude' not on PATH — install Claude Code, or pick another provider.", fg="yellow", err=True)

    brain.save_config(cfg)
    typer.secho(f"\nSaved -> active provider: {brain.provider()}", fg="green")


@app.command()
def config():
    """Show the gitly brain configuration (provider + key sources; values never printed)."""
    from backend.app.engines.copilot import brain

    _show_brain(brain)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
