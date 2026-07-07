"""gitly CLI — `gitly trace`, `gitly scan`, plus seams for `shrink` / `lens`."""
from __future__ import annotations

import json
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
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True, timeout=30
        )
        return Path(out.stdout.strip())
    except Exception:
        return Path.cwd()


def _tracked_files(root: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, timeout=30)
    return out.stdout.splitlines()


def _git_user(root: Path) -> str:
    out = subprocess.run(["git", "-C", str(root), "config", "user.name"], capture_output=True, text=True, timeout=30)
    return out.stdout.strip() or "unknown"


def _tag(ln) -> str:
    if ln.author_type.value == "human":
        return "human"
    badge = ln.model or ln.agent.value
    mark = "~" if ln.inferred else ""           # ~ = inferred, not recorded
    if ln.author_type.value == "hybrid":        # AI-written, then materially human-edited
        return f"hybrid:{badge}{mark} ({int(round(ln.human_edit_ratio * 100))}% human)"
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


def _warn_unbound(root: Path) -> None:
    """Committed-but-never-bound events can't attribute committed lines (events only explain
    uncommitted ones) — say so instead of silently under-reporting AI lines. Events whose file
    is still dirty are healthy pending captures, not stale, so they don't count."""
    try:
        from backend.app.engines.trace.binder import _rel
        from backend.app.engines.trace.recorder import read_bound_ids, read_events
        pending = [e for e in read_events(root) if e.event_id not in read_bound_ids(root)]
        if not pending:
            return
        out = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                             capture_output=True, text=True, timeout=30).stdout
        dirty = {ln[3:].split(" -> ")[-1].strip().strip('"') for ln in out.splitlines() if len(ln) > 3}
        stale = [e for e in pending if _rel(root, e.file_path) not in dirty]
    except Exception:
        return
    if stale:
        typer.secho(
            f"note: {len(stale)} captured event(s) were never bound to their commit — those AI lines "
            "show as inferred/human. Fix now with `gitly bind --backfill`; prevent it with `gitly init` "
            "(installs the post-commit hook).",
            fg="yellow", err=True,
        )


@trace_app.callback(invoke_without_command=True)
def trace_default(
    ctx: typer.Context,
    file: str = typer.Argument(None, help="File to trace (blame-style provenance)."),
    summary: bool = typer.Option(False, "--summary", help="Repo rollup instead of per-line."),
    json_out: bool = typer.Option(False, "--json", help="Machine-readable output (for CI/tooling)."),
    max_unreviewed: int = typer.Option(
        None, "--max-unreviewed",
        help="CI gate: exit 1 if unreviewed AI-origin lines exceed this (use 0 to require full review).",
    ),
):
    if ctx.invoked_subcommand is not None:
        return
    root = _repo_root()
    _warn_unbound(root)
    if summary or not file or max_unreviewed is not None:
        files = [file] if file else _tracked_files(root)
        all_lines = []
        for f in files:
            try:
                all_lines += trace_file(root, f)
            except Exception:
                continue
        s = summarize(all_lines, repo=root.name)
        typer.echo(s.model_dump_json(indent=2) if json_out else _render_summary(s))
        if max_unreviewed is not None and s.unreviewed_ai_lines > max_unreviewed:
            typer.secho(
                f"x {s.unreviewed_ai_lines} unreviewed AI line(s) > allowed {max_unreviewed} — "
                "run `gitly review <files>` to sign off.", fg="red", err=True)
            raise typer.Exit(1)
        return
    try:
        lines = trace_file(root, file)
    except subprocess.CalledProcessError:
        typer.secho(f"Can't trace '{file}' — it isn't a tracked file in {root.name} "
                    "(check the path, and make sure it's committed).", fg="red", err=True)
        raise typer.Exit(1)
    if json_out:
        typer.echo(json.dumps([ln.model_dump(mode="json") for ln in lines], indent=2))
        return
    for ln in lines:
        typer.echo(f"{ln.line_no:>5}  {_tag(ln):<26} {ln.content}")


@app.command("bind")
def bind(
    repo: str = typer.Option(".", "--repo", help="Path to the git repo"),
    quiet: bool = typer.Option(False, "--quiet", help="Say nothing on success (for the post-commit hook)"),
    do_backfill: bool = typer.Option(
        False, "--backfill",
        help="Also bind stranded old events (committed without the hook) to the commit that introduced them.",
    ),
):
    """Bind captured AI-authorship events to the latest commit, computing the human-edit ratio.

    Runs automatically via the post-commit hook `gitly init` installs; safe to run by hand.
    This is what lets `gitly trace` show real edit ratios and hybrid lines offline."""
    from backend.app.engines.trace.binder import backfill, bind_head

    root = Path(repo if repo != "." else str(_repo_root()))
    try:
        sha, records = bind_head(root)
        rescued = backfill(root) if do_backfill else []
    except Exception as e:  # never disrupt a commit
        if not quiet:
            typer.secho(f"bind skipped: {e}", fg="yellow", err=True)
        return
    if not quiet:
        if records:
            typer.secho(f"bound {len(records)} authorship event(s) to {sha[:8]}", fg="green")
        for bsha, n in rescued:
            typer.secho(f"backfilled {n} event(s) to {bsha[:8]}", fg="green")
        if not records and not rescued:
            typer.echo("nothing to bind")


def _parse_gh_pr_list(payload: str) -> tuple[list[int], set[str]]:
    """(APPROVED merged-PR numbers, human approver logins) from
    `gh pr list --json number,reviewDecision,latestReviews` output. Commits are fetched
    per-PR afterwards — asking for them in the list query blows GitHub's GraphQL node budget."""
    numbers: list[int] = []
    approvers: set[str] = set()
    for pr in json.loads(payload or "[]"):
        if pr.get("reviewDecision") != "APPROVED":
            continue
        if isinstance(pr.get("number"), int):
            numbers.append(pr["number"])
        for rv in pr.get("latestReviews") or []:
            login = ((rv.get("author") or {}).get("login") or "").strip()
            if rv.get("state") == "APPROVED" and login and "bot" not in login.lower():
                approvers.add(login)
    return numbers, approvers


@app.command()
def review(
    paths: list[str] = typer.Argument(None, help="File(s) whose AI lines to mark reviewed"),
    commit: list[str] = typer.Option(None, "--commit", help="Specific commit SHA(s) to mark reviewed (repeatable)"),
    all_files: bool = typer.Option(False, "--all", help="Mark every AI line in the repo reviewed"),
    from_github: bool = typer.Option(
        False, "--from-github",
        help="Automated: harvest merged-PR approvals via the `gh` CLI and mark their commits reviewed.",
    ),
    limit: int = typer.Option(200, "--limit", help="How many recent merged PRs --from-github scans"),
    show: bool = typer.Option(False, "--list", help="List reviewed commits and exit"),
    by: str = typer.Option(None, "--by", help="Reviewer name (default: your git user.name)"),
    repo: str = typer.Option(".", "--repo", help="Path to the git repo"),
):
    """Sign off on AI-authored code — clears it from `unreviewed AI lines`.

    Three ways review gets recorded: explicit (`gitly review app.py` / `--commit` / `--all`),
    harvested from GitHub PR approvals (`--from-github`; run it in CI after merges), or a
    `Reviewed-by:`/`Acked-by:` commit trailer (picked up automatically, no command needed)."""
    from backend.app.engines.trace.blame import trace_file
    from backend.app.engines.trace.recorder import mark_reviewed, read_reviewed

    root = Path(repo if repo != "." else str(_repo_root()))
    if from_github:
        def _gh(*args: str) -> str:
            try:
                p = subprocess.run(["gh", *args], capture_output=True, text=True, cwd=root, timeout=120)
            except FileNotFoundError:
                typer.secho("`gh` CLI not found — install https://cli.github.com and `gh auth login`.",
                            fg="red", err=True)
                raise typer.Exit(1)
            if p.returncode != 0:
                typer.secho(f"gh failed: {p.stderr.strip()}", fg="red", err=True)
                raise typer.Exit(1)
            return p.stdout

        numbers, approvers = _parse_gh_pr_list(_gh(
            "pr", "list", "--state", "merged", "--limit", str(limit),
            "--json", "number,reviewDecision,latestReviews"))
        if not numbers:
            typer.echo("No approved merged PRs found — nothing to sync.")
            return
        gh_shas: set[str] = set()
        for num in numbers:   # commits per approved PR only — cheap, and few of them
            gh_shas.update(s for s in _gh("pr", "view", str(num), "--json", "commits",
                                          "--jq", ".commits[].oid").split() if s)
        who = ("github:" + ",".join(sorted(approvers))) if approvers else "github"
        n = mark_reviewed(root, sorted(gh_shas), by=who)
        typer.secho(
            f"Synced GitHub approvals: {n} newly reviewed commit(s) "
            f"(from {len(gh_shas)} commit(s) across {len(numbers)} approved PR(s)).", fg="green")
        return
    if show:
        rv = read_reviewed(root)
        typer.echo(f"{len(rv)} reviewed commit(s)")
        for s in sorted(rv):
            typer.echo(f"  {s[:12]}")
        return

    shas: set[str] = set(commit or [])
    files = _tracked_files(root) if all_files else (paths or [])
    ai_lines = 0
    for f in files:
        try:
            for ln in trace_file(root, f):
                if ln.author_type.value != "human" and ln.commit_sha:
                    shas.add(ln.commit_sha)
                    ai_lines += 1
        except Exception:
            continue
    if not shas:
        typer.secho("Nothing to review — pass file(s), --commit <sha>, or --all.", fg="yellow", err=True)
        raise typer.Exit(1)
    reviewer = by or _git_user(root)
    n = mark_reviewed(root, list(shas), by=reviewer)
    scope = "the whole repo" if all_files else (", ".join(files) if files else f"{len(commit or [])} commit(s)")
    detail = f" ({ai_lines} AI line(s))" if files else ""
    typer.secho(f"Reviewed by {reviewer}: marked {n} new commit(s){detail} across {scope}.", fg="green")
    typer.echo("Run `gitly trace --summary` to see the unreviewed count drop.")


@app.command()
def sync(
    paths: list[str] = typer.Argument(None, help="File(s) to sync (default: all tracked files)"),
    key: str = typer.Option(None, "--key", help="Dashboard key — the exact value to type in the /trace box (default: your git origin URL)"),
    reset: bool = typer.Option(False, "--reset", help="Clear this key's existing records first (so re-syncs replace, not accumulate)"),
    api: str = typer.Option("http://localhost:8000", "--api", help="gitly backend URL"),
    repo: str = typer.Option(".", "--repo", help="Path to the git repo"),
):
    """Push this repo's REAL provenance to the backend so the web dashboard shows it.

    `gitly trace` reads your local ledger; the dashboard reads the database — this bridges
    them (the seed script only plants fixtures). Then open /trace with the printed key."""
    from backend.app.engines.trace.sync import build_records, clear_records, origin_repo_key, push_records

    root = Path(repo if repo != "." else str(_repo_root()))
    dash_key = key or origin_repo_key(root)
    files = list(paths) if paths else _tracked_files(root)
    if not files:
        typer.secho("Nothing to sync.", fg="yellow", err=True)
        raise typer.Exit(1)
    typer.echo(f"Tracing {len(files)} file(s) for '{dash_key}' …")
    records = build_records(root, dash_key, files)
    if not records:
        typer.secho("No provenance to sync (no traceable lines found).", fg="yellow", err=True)
        raise typer.Exit(1)
    try:
        if reset:
            cleared = clear_records(api, dash_key)
            typer.echo(f"  reset: cleared {cleared} existing record(s) for '{dash_key}'")
        n = push_records(api, records)
    except Exception as e:
        typer.secho(f"Could not reach the backend at {api}: {e}\n"
                    "Is it running? Start it with `make up` (or `make api`).", fg="red", err=True)
        raise typer.Exit(1)
    typer.secho(f"Synced {n} record(s) for '{dash_key}'.", fg="green")
    typer.echo(f"Open: http://localhost:3000/trace?repo={dash_key}")


@app.command()
def backfill(
    agent: str = typer.Option("claude_code", "--agent", help="Agent to attribute existing code to"),
    model: str = typer.Option(None, "--model", help="Model name to record (optional; omit = unknown)"),
    exclude: str = typer.Option("", "--exclude", help="Comma-separated globs to skip (e.g. '*.md,*.lock')"),
    repo: str = typer.Option(".", "--repo", help="Path to the git repo"),
):
    """Attest that the EXISTING tracked code was AI-authored — a one-time backfill for a repo
    built before capture was on, so `gitly trace` / the dashboard reflect it.

    This is YOUR attestation (whole-file, your say-so), not captured per-keystroke truth. It
    attributes every tracked file (minus --exclude) to --agent; refine with --exclude."""
    import fnmatch
    import hashlib
    from datetime import UTC, datetime

    from backend.app.engines.trace.recorder import write_records
    from shared.schema.provenance import AgentKind, AuthorType, ProvenanceRecord

    root = Path(repo if repo != "." else str(_repo_root()))
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
    ).stdout.strip() or "0" * 40
    skip = (*(g.strip() for g in exclude.split(",") if g.strip()),
            "*.lock", "*-lock.json", "*.min.js", "*.min.css", "*.map", "*.png", "*.jpg",
            "*.jpeg", "*.gif", "*.svg", "*.ico", "*.webp", "*.woff", "*.woff2", "*.ttf", "*.pdf")
    now = datetime.now(UTC)
    records: list[ProvenanceRecord] = []
    skipped = 0
    for f in _tracked_files(root):
        if any(fnmatch.fnmatch(f, g) for g in skip):
            skipped += 1
            continue
        try:
            content = (root / f).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped += 1
            continue
        n = len(content.splitlines())
        if n == 0:
            continue
        rid = hashlib.sha256(f"backfill:{root.name}:{f}".encode()).hexdigest()[:32]
        records.append(ProvenanceRecord(
            record_id=rid, repo=root.name, commit_sha=head, file_path=f,
            line_start=1, line_end=n, author_type=AuthorType.ai,
            model=model, agent=AgentKind(agent), content=content,
            human_edit_ratio=0.0, created_at=now, bound_at=now,
        ))
    if not records:
        typer.secho("Nothing to backfill.", fg="yellow", err=True)
        raise typer.Exit(1)
    write_records(root, records)
    lines = sum(r.line_end for r in records)
    label = f"AI:{agent}" + (f" / {model}" if model else "")
    typer.secho(f"Backfilled {len(records)} file(s) (~{lines} lines) as {label}. Skipped {skipped}.", fg="green")
    typer.echo("Attested (your say-so, edit-ratio 0). See `gitly trace --summary`; "
               "push to the dashboard with `gitly sync --reset`.")


@app.command()
def scan(staged: bool = typer.Option(False, "--staged", help="Scan staged changes (for a pre-commit hook).")):
    """Secret firewall: block secrets before they're committed."""
    root = _repo_root()
    if staged:
        text = subprocess.run(
            ["git", "-C", str(root), "diff", "--cached"], capture_output=True, text=True, timeout=60
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
    pr: bool = typer.Option(False, "--pr", help="Push the slices and open chained stacked PRs on GitHub"),
    remote: str = typer.Option("origin", "--remote", help="Remote to push slice branches to"),
    check: str = typer.Option(None, "--check", help="Run this build/test command against EACH slice; a red slice blocks --pr"),
    docker: str = typer.Option(None, "--docker", help="Run --check inside this Docker image (real isolation)"),
    llm: bool = typer.Option(False, "--llm", help="Use the LLM labeler (needs GITLY_ANTHROPIC_API_KEY)"),
):
    """Split a PR (base..head) into a verified stack of small sub-PRs.

    Add --pr to push each slice and open a chained stack of PRs on GitHub (slice N based on
    slice N-1). Add --check "<cmd>" to prove every slice builds/tests green in isolation
    before shipping. Never shipped unless completeness verifies."""
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
    make_refs = write_refs or pr or bool(check)   # branches/commits needed to ship or validate
    res = run_shrink(root, base, head, opts=PlanOptions(**preset), write_refs=make_refs, prefer_llm=llm)
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
    if make_refs and res.materialized:
        typer.echo("branches:")
        for sc in res.materialized.slices:
            typer.echo(f"  {sc.branch}  ({sc.commit_sha[:10]})")
    if check:
        from backend.app.engines.shrink.validate import validate_stack

        where = f" inside {docker}" if docker else ""
        typer.echo(f"\nvalidating each slice{where}: `{check}`")
        results = validate_stack(root, res, check, docker_image=docker)
        for c in results:
            typer.secho(f"  {'✓' if c.ok else '✗'} #{c.order}  {c.title}", fg="green" if c.ok else "red")
            if not c.ok:
                for ln in c.output.splitlines()[-4:]:
                    typer.echo(f"        {ln}")
        if any(not c.ok for c in results):
            typer.secho("x: a slice failed validation — not shipping. (Fix the ordering / split.)", fg="red", err=True)
            raise typer.Exit(1)
        typer.secho("ok: every slice is green ✅", fg="green")
    if pr:
        from backend.app.engines.shrink.ship import compare_url, open_pr, pr_specs, push_branches, remote_slug

        specs = pr_specs(res)
        if not specs:
            typer.secho("No materialized branches to ship.", fg="yellow", err=True)
            raise typer.Exit(1)
        typer.echo(f"\npushing {len(specs)} slice branch(es) to {remote}…")
        try:
            push_branches(root, [s["branch"] for s in specs], remote=remote)
        except Exception as e:
            typer.secho(f"push failed: {e}", fg="red", err=True)
            raise typer.Exit(1)
        slug = remote_slug(root)
        typer.echo("opening stacked PRs:")
        for sp in specs:
            ok, info = open_pr(root, sp)
            if ok:
                typer.secho(f"  ✓ {sp['branch']} → {sp['base']}   {info}", fg="green")
            else:
                url = compare_url(slug, sp["base"], sp["branch"]) if slug else "(no origin remote)"
                typer.secho(f"  ! {sp['branch']} → {sp['base']}  (gh couldn't open it; create manually: {url})", fg="yellow")


@app.command()
def lens(
    file: str = typer.Argument(None, help="Unified .diff file to analyze (omit or '-' to read stdin)"),
    sites: bool = typer.Option(False, "--sites", help="List each cluster's individual change sites"),
    json_out: bool = typer.Option(False, "--json", help="Emit the raw AnalysisResult as JSON"),
):
    """Cluster a diff into conceptual change cards (renames, insertions, outliers).

    Reads a unified diff from a file or stdin — e.g. `git diff main | gitly lens`."""
    from backend.app.engines.lens.engine import analyze, make_source
    from backend.app.engines.lens.models import Confidence, SourceType

    if file and file != "-":
        try:
            diff_text = Path(file).read_text()
        except OSError as e:
            typer.secho(f"Could not read {file}: {e}", fg="red", err=True)
            raise typer.Exit(1)
    else:
        diff_text = sys.stdin.read()
    if not diff_text.strip():
        typer.secho("No diff provided — pass a file or pipe a unified diff on stdin.", fg="red", err=True)
        raise typer.Exit(1)

    try:
        res = analyze(diff_text, make_source(SourceType.raw_diff))
    except Exception as e:
        typer.secho(f"Could not parse diff: {e}", fg="red", err=True)
        raise typer.Exit(1)

    if json_out:
        typer.echo(res.model_dump_json(indent=2))
        return

    s = res.stats
    typer.secho(res.title or "lens analysis", bold=True)
    typer.echo(f"  {s.files_changed} files  +{s.lines_added}/-{s.lines_removed}  "
               f"{s.hunk_count} hunks  ->  {s.cluster_count} clusters")
    hue = {Confidence.high: typer.colors.GREEN, Confidence.medium: typer.colors.YELLOW,
           Confidence.low: typer.colors.BRIGHT_BLACK}
    rank = {Confidence.high: 0, Confidence.medium: 1, Confidence.low: 2}
    for c in sorted(res.clusters, key=lambda c: (rank[c.confidence], -c.site_count)):
        scope = (f"{c.site_count} site{'s' if c.site_count != 1 else ''}"
                 f" / {c.file_count} file{'s' if c.file_count != 1 else ''}")
        dot = typer.style("●", fg=hue[c.confidence])
        typer.echo(f"\n  {dot} {c.kind.value}: {c.title}   [{scope}]  ({c.confidence.value})")
        detail = c.description or c.confidence_reason
        if detail:
            typer.echo(f"      {detail}")
        if sites:
            for site in c.sites[:12]:
                typer.echo(f"        · {site.label}")
            if len(c.sites) > 12:
                typer.echo(f"        · (+{len(c.sites) - 12} more)")
        for o in c.outliers:
            typer.secho(f"      ! outlier: {o.reason}", fg=typer.colors.YELLOW)
    for w in res.warnings:
        typer.secho(f"  warning: {w}", fg=typer.colors.YELLOW)


@app.command()
def commit(
    message_arg: str = typer.Argument(None, metavar="[MESSAGE]", help="Commit message (omit to auto-generate from the diff)"),
    message: str = typer.Option(None, "-m", "--message", help="Commit message, git-style (alias for the positional)"),
    all: bool = typer.Option(False, "--all", "-a", help="Stage all changes, including untracked files"),
    path: list[str] = typer.Option(None, "--path", help="Stage only these path(s) (repeatable)"),
    split: bool = typer.Option(False, "--split", help="Auto-split the working tree into several logical commits"),
    llm: bool = typer.Option(False, "--llm", help="Force the LLM to write the message(s)"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Never call an LLM — use the offline heuristic"),
    repo: str = typer.Option(".", "--repo", help="Path to the git repo"),
):
    """Commit cleanly: stage safe files, block on secrets, refuse on a protected branch.

    Pass a message as `-m "..."` (git-style) or positionally; omit it and gitly writes a
    conventional one from the diff — via your configured brain (see `gitly auth`) or, with
    none, an offline heuristic. Use --split to break a big working tree into several
    independently-reviewable commits.

    The safe-add guard never stages .env / keys / build junk; pass them with --path
    only if you truly mean to."""
    from backend.app.engines.copilot.ops import GitError, safe_commit, split_commit

    cwd = repo if repo != "." else str(_repo_root())
    mode = "off" if no_llm else "llm" if llm else "auto"
    text = message or message_arg

    try:
        if split:
            ok, lines = split_commit(cwd, stage_all=all, msg_mode=mode)
            typer.secho("Split into commits:" if ok else "Could not split:", fg="green" if ok else "red", err=not ok)
            for ln in lines:
                typer.echo(ln)
            raise typer.Exit(0 if ok else 1)
        ok, msg = safe_commit(cwd, text, stage_all=all, paths=path, msg_mode=mode)
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


@app.command()
def doctor():
    """Diagnose the gitly setup: repo, hooks, ledger, brain, backend — and how to fix each."""
    import urllib.request
    from backend.app.engines.copilot import brain
    from backend.app.engines.trace.recorder import read_bound_ids, read_events, read_records

    def row(state: bool | None, label: str, detail: str, fix: str = "") -> None:
        mark = "✓" if state else ("-" if state is None else "x")
        color = "green" if state else (None if state is None else "red")
        line = f" {typer.style(mark, fg=color)} {label:<28} {detail}"
        typer.echo(line + (f"\n   fix: {fix}" if fix and state is False else ""))

    def _has(hook: Path) -> bool:
        try:
            return "gitly" in hook.read_text(encoding="utf-8")
        except OSError:
            return False

    root = _repo_root()
    in_repo = (root / ".git").exists()
    row(in_repo, "git repository", str(root) if in_repo else "not a git repo", "git init")
    if not in_repo:
        raise typer.Exit(1)

    row(_has(root / ".git" / "hooks" / "pre-commit"), "secret pre-commit hook",
        "blocks committed secrets", "gitly init")
    row(_has(root / ".git" / "hooks" / "post-commit"), "bind post-commit hook",
        "binds AI authorship to each commit", "gitly init")
    claude_settings = root / ".claude" / "settings.json"
    captured = claude_settings.exists() and "claude_post_tool" in claude_settings.read_text(encoding="utf-8")
    row(True if captured else None, "Claude Code capture hook",
        "records what the agent writes" if captured else "not registered (fine if you don't use Claude Code)",
        "gitly init --claude-code")

    events, records = read_events(root), read_records(root)
    pending = [e for e in events if e.event_id not in read_bound_ids(root)]
    stale_hint = "  — run `gitly bind --backfill`" if pending else ""
    row(True, "provenance ledger",
        f"{len(events)} event(s) · {len(records)} bound record(s) · {len(pending)} pending{stale_hint}")

    prov = brain.provider()
    row(True, "brain (commit messages)",
        prov + ("" if prov != "heuristic" else " — offline fallback; `gitly auth` enables LLM messages"))

    api = os.environ.get("GITLY_API_URL", "http://localhost:8000")
    try:
        urllib.request.urlopen(f"{api}/health", timeout=2)
        row(True, "backend API", api)
    except Exception:
        row(None, "backend API", f"{api} unreachable — optional (dashboard/MCP scan only); `make up` starts it")


_PRE_COMMIT_HOOK = """#!/usr/bin/env bash
# gitly pre-commit hook — block secrets before they're committed. (installed by `gitly init`)
set -euo pipefail
if command -v gitly >/dev/null 2>&1; then
  gitly scan --staged || exit 1
else
  # fallback if gitly isn't on PATH: scan the staged diff for the highest-signal patterns
  if git diff --cached | grep -Eq 'AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{36,}|sk-(ant-)?[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----'; then
    echo "x gitly: potential secret in staged changes — commit blocked (install gitly for the full scan)"
    exit 1
  fi
fi
"""

_POST_COMMIT_HOOK = """#!/usr/bin/env bash
# gitly post-commit hook — bind AI-authorship events to this commit. (installed by `gitly init`)
# Non-blocking and silent: it never affects the commit that just happened.
command -v gitly >/dev/null 2>&1 && gitly bind --quiet >/dev/null 2>&1 || true
"""


def _install_claude_hook(root: Path) -> str:
    """Register the authorship-capture PostToolUse hook in <root>/.claude/settings.json."""
    import backend
    script = Path(backend.__file__).resolve().parent.parent / "sdk" / "hooks" / "claude_post_tool.py"
    if not script.exists():
        return ("skipped Claude Code hook — capture script not found; use the gitly Claude Code "
                "plugin instead (see docs: Integrations → MCP & Claude Code)")
    settings = root / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if settings.exists():
        try:
            data = json.loads(settings.read_text())
        except json.JSONDecodeError:
            return f"skipped Claude Code hook — {settings} is not valid JSON; edit it by hand"
    cmd = f"python3 {script}"
    post = data.setdefault("hooks", {}).setdefault("PostToolUse", [])
    if any(h.get("command") == cmd for e in post if isinstance(e, dict) for h in e.get("hooks", [])):
        return f"Claude Code capture hook already present in {settings}"
    post.append({"matcher": "Edit|Write|MultiEdit", "hooks": [{"type": "command", "command": cmd}]})
    settings.write_text(json.dumps(data, indent=2) + "\n")
    return f"registered Claude Code authorship-capture hook -> {settings}"


@app.command()
def init(
    claude_code: bool = typer.Option(False, "--claude-code", help="Also register the Claude Code authorship-capture hook"),
    force: bool = typer.Option(False, "--force", help="Replace an existing non-gitly pre-commit hook (backs it up)"),
    repo: str = typer.Option(".", "--repo", help="Path to the git repo"),
):
    """Set up gitly in this repo: install the secret-blocking **pre-commit** hook and the
    authorship-binding **post-commit** hook (and, with --claude-code, the capture hook)."""
    root = Path(repo if repo != "." else str(_repo_root()))
    git_dir = root / ".git"
    if not git_dir.is_dir():
        typer.secho(f"Not a git repository: {root}  (run `git init` first).", fg="red", err=True)
        raise typer.Exit(1)

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hooks = [
        ("pre-commit", _PRE_COMMIT_HOOK, "blocks secrets before they're committed"),
        ("post-commit", _POST_COMMIT_HOOK, "binds AI authorship to each commit"),
    ]
    # guard pass — refuse to clobber a foreign hook unless --force (check all before writing any)
    for name, _content, _desc in hooks:
        p = hooks_dir / name
        if p.exists() and "gitly" not in p.read_text(errors="ignore") and not force:
            typer.secho(f"A non-gitly {name} hook already exists at {p}.\n"
                        "Re-run with --force to back it up and replace it.", fg="yellow", err=True)
            raise typer.Exit(1)
    done: list[str] = []
    for name, content, desc in hooks:
        p = hooks_dir / name
        if p.exists() and "gitly" not in p.read_text(errors="ignore"):
            backup = p.with_name(f"{name}.bak")
            p.replace(backup)
            done.append(f"backed up existing {name} -> {backup.name}")
        p.write_text(content)
        p.chmod(0o755)
        done.append(f"installed {name} hook ({desc})")

    if claude_code:
        done.append(_install_claude_hook(root))

    typer.secho("gitly initialized:", fg="green")
    for d in done:
        typer.echo(f"  - {d}")
    typer.echo("\nTest it: stage a fake key and run `git commit` — the hook will block it.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
