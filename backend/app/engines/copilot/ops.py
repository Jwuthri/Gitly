"""Copilot git operations for the terminal: commit cleanly (smart message + safe staging),
absorb working changes into the right earlier commit(s), and split a working tree into
several logical commits. Pure local git + the secret firewall + the gitly brain."""
from __future__ import annotations

import json
import os
import subprocess

from backend.app.security.secret_firewall import scan

PROTECTED = {"main", "master", "develop", "release"}


class GitError(RuntimeError):
    pass


def _git(cwd: str, *args: str, env: dict | None = None, check: bool = True) -> str:
    p = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True, text=True, env={**os.environ, **(env or {})}, timeout=60,
    )
    if check and p.returncode != 0:
        raise GitError(p.stderr.strip())
    return p.stdout


def _branch(cwd: str) -> str:
    try:
        return _git(cwd, "rev-parse", "--abbrev-ref", "HEAD").strip()
    except GitError:
        return ""


# ---- safe-add guard: never stage credentials / build junk by accident ----

_RISKY_DIRS = ("node_modules/", "dist/", "build/", ".next/", "__pycache__/", ".venv/", "venv/", ".git/", "vendor/")
_RISKY_NAMES = {".DS_Store", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials"}
_RISKY_SUFFIX = (".pem", ".key", ".p12", ".pfx", ".keystore", ".log")


def _risky(path: str) -> str | None:
    base = path.rsplit("/", 1)[-1]
    if base == ".env" or base.startswith(".env."):
        return "looks like an env/secret file"
    if base in _RISKY_NAMES:
        return "looks like a credential file"
    if base.endswith(_RISKY_SUFFIX):
        return f"{base.rsplit('.', 1)[-1]} file (often not meant for git)"
    if any(seg in f"{path}/" for seg in _RISKY_DIRS):
        return "build/vendor artifact"
    return None


def _stage_candidates(cwd: str, stage_all: bool) -> tuple[list[str], list[tuple[str, str]]]:
    """(safe files to stage, [(risky file, reason)]). Tracked changes vs HEAD, plus
    untracked files when stage_all."""
    try:
        tracked = [ln.strip() for ln in _git(cwd, "diff", "HEAD", "--name-only").splitlines() if ln.strip()]
    except GitError:
        tracked = []
    untracked = (
        [ln.strip() for ln in _git(cwd, "ls-files", "--others", "--exclude-standard").splitlines() if ln.strip()]
        if stage_all else []
    )
    cand = list(dict.fromkeys(tracked + untracked))
    safe: list[str] = []
    risky: list[tuple[str, str]] = []
    for f in cand:
        r = _risky(f)
        if r:
            risky.append((f, r))
        else:
            safe.append(f)
    return safe, risky


def _excluded_note(excluded: list[tuple[str, str]]) -> str:
    if not excluded:
        return ""
    items = "; ".join(f"{f} ({r})" for f, r in excluded[:5])
    return f"\n  ! skipped {len(excluded)} risky file(s) — add explicitly with --path if intended: {items}"


# ---- commit-message generation -------------------------------------------

_DEPS = {
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "pyproject.toml",
    "poetry.lock", "requirements.txt", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock",
    "Gemfile", "Gemfile.lock",
}


def _category(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    if base in _DEPS or path.endswith((".lock", ".toml", ".yml", ".yaml", ".ini")) or "Dockerfile" in base:
        return "chore"
    if ("/tests/" in path or "/__tests__/" in path or base.startswith("test_")
            or "_test." in base or ".test." in base or ".spec." in base):
        return "test"
    if base.endswith((".md", ".rst", ".mdx")) or "/docs/" in path or base.upper().startswith("README"):
        return "docs"
    return "src"


def auto_message(diff_text: str, *, mode: str = "auto") -> str:
    """Conventional message for a diff. mode: 'auto' (brain if available, else heuristic),
    'llm' (force brain), 'off' (heuristic only)."""
    if mode != "off":
        from backend.app.engines.copilot import brain
        if mode == "llm" or brain.available():
            m = brain.complete(
                "Write ONE conventional-commit message (`type: subject`, under 72 chars, no body) "
                f"for this diff. Reply with ONLY the message line.\n\n{diff_text[:8000]}",
                max_tokens=40,
            )
            if m:
                return m.splitlines()[0].strip().strip("`").strip()
    return _heuristic_message(diff_text)


def _heuristic_message(diff_text: str) -> str:
    """Key-free fallback: derive `type: subject` from the lens engine's clusters + files."""
    try:
        from backend.app.engines.lens.engine import analyze, make_source
        from backend.app.engines.lens.models import ClusterKind, Confidence, SourceType
        res = analyze(diff_text, make_source(SourceType.raw_diff))
    except Exception:
        return "update changes"
    cats = {_category(f.path) for f in res.files}
    statuses = {f.status.value for f in res.files}
    rank = {Confidence.high: 0, Confidence.medium: 1, Confidence.low: 2}
    clusters = sorted(res.clusters, key=lambda c: (rank[c.confidence], -c.site_count))
    top = clusters[0] if clusters else None
    refactor = {ClusterKind.rename, ClusterKind.import_migration, ClusterKind.signature_change,
                ClusterKind.api_replacement, ClusterKind.type_change}
    if cats == {"test"}:
        typ = "test"
    elif cats == {"docs"}:
        typ = "docs"
    elif cats == {"chore"}:
        typ = "chore"
    elif top and top.confidence != Confidence.low and top.kind in refactor:
        typ = "refactor"
    elif "added" in statuses:
        typ = "feat"
    else:
        typ = "chore"
    if top and top.confidence != Confidence.low:
        subject = top.title.replace("`", "")
    else:
        names = [f.path.rsplit("/", 1)[-1] for f in res.files]
        subject = "update " + ", ".join(names[:3]) + (f" (+{len(names) - 3} more)" if len(names) > 3 else "")
    subject = (subject[:1].lower() + subject[1:]) if subject else "update changes"
    return f"{typ}: {subject}"


# ---- commit ---------------------------------------------------------------

def safe_commit(cwd: str, message: str | None = None, *, stage_all: bool = False,
                paths: list[str] | None = None, msg_mode: str = "auto") -> tuple[bool, str]:
    """Stage (safe files only) → block on secrets → refuse on a protected branch → commit.
    Message: explicit, else generated (brain/heuristic)."""
    branch = _branch(cwd)
    if branch in PROTECTED:
        return False, f"Refusing to commit to protected branch '{branch}'. Create a feature branch first."
    excluded: list[tuple[str, str]] = []
    if paths:
        try:
            _git(cwd, "add", "--", *paths)        # explicit paths: trust the user
        except GitError as e:
            if "ignored by one of your" in str(e):
                return False, ("Those path(s) are gitignored — often secrets or build output, "
                               "so gitly won't force-add them. If you're certain, run `git add -f` first.")
            return False, f"Could not stage {', '.join(paths)}: {e}"
    else:
        safe, excluded = _stage_candidates(cwd, stage_all)
        if safe:
            _git(cwd, "add", "--", *safe)
    staged = _git(cwd, "diff", "--cached")
    if not staged.strip():
        hint = "" if excluded else " (use --all for new files, or --path to pick files)"
        return False, f"Nothing staged to commit.{hint}{_excluded_note(excluded)}"
    findings = scan(staged)
    if findings:
        _git(cwd, "reset", "-q", check=False)
        lst = "\n".join(f"  - {f.kind} (line {f.line_no})" for f in findings[:10])
        return False, f"Commit BLOCKED — staged changes contain secrets:\n{lst}\n(changes unstaged) Remove them and retry."
    if not message:
        message = auto_message(staged, mode=msg_mode)
    n = len([ln for ln in _git(cwd, "diff", "--cached", "--name-only").splitlines() if ln.strip()])
    _git(cwd, "commit", "-q", "-m", message)
    head = _git(cwd, "rev-parse", "--short", "HEAD").strip()
    return True, f"Committed {head} on {branch} ({n} file{'s' if n != 1 else ''}): {message}{_excluded_note(excluded)}"


# ---- semantic split: one working tree -> several logical commits ----------

def _heuristic_groups(cwd: str, files: list[str]) -> list[tuple[str | None, list[str]]]:
    from collections import OrderedDict
    buckets: "OrderedDict[tuple[str, str], list[str]]" = OrderedDict()
    for f in files:
        cat = _category(f)
        mod = "/".join(f.split("/")[:2]) if (cat == "src" and "/" in f) else cat
        buckets.setdefault((cat, mod), []).append(f)
    order = {"chore": 0, "src": 1, "test": 2, "docs": 3}
    items = sorted(buckets.items(), key=lambda kv: (order.get(kv[0][0], 1), kv[0][1]))
    # Message is None here → split_commit fills it from the *staged* diff (so new/untracked
    # files, which never appear in `git diff HEAD`, still get a real message).
    return [(None, fs) for (_cat, _mod), fs in items]


def _diff_vs_head(cwd: str, files: list[str]) -> str:
    """Unified diff of `files` vs HEAD, INCLUDING untracked files (plain `git diff`
    omits them). Intent-to-adds the untracked ones, diffs, then restores the index."""
    untracked = [f for f in _git(cwd, "ls-files", "--others", "--exclude-standard", "--", *files).splitlines() if f.strip()]
    if untracked:
        _git(cwd, "add", "-N", "--", *untracked, check=False)
    try:
        return _git(cwd, "diff", "HEAD", "--", *files)
    finally:
        if untracked:
            _git(cwd, "reset", "-q", "--", *untracked, check=False)  # undo intent-to-add


def _brain_groups(cwd: str, files: list[str]) -> list[tuple[str, list[str]]] | None:
    from backend.app.engines.copilot import brain
    diff = _diff_vs_head(cwd, files)
    out = brain.complete(
        "Group these changed files into a few logical, independently-reviewable commits "
        "(deps/config first, then source, then tests, then docs is a good default). "
        'Reply with ONLY a JSON array: [{"message":"type: subject","files":["path",...]}]. '
        "Every file must appear in exactly one group.\n\nfiles:\n"
        + "\n".join(files) + f"\n\ndiff:\n{diff[:12000]}",
        max_tokens=900,
    )
    if not out:
        return None
    try:
        arr = json.loads(out[out.index("["): out.rindex("]") + 1])
        grouped = [f for g in arr for f in g.get("files", [])]
    except Exception:
        return None
    if set(grouped) != set(files):  # model didn't cover exactly -> fall back
        return None
    return [(g.get("message", "chore: update"), g["files"]) for g in arr if g.get("files")]


def split_commit(cwd: str, *, stage_all: bool = False, msg_mode: str = "auto") -> tuple[bool, list[str]]:
    """Split the working tree into several logical commits (brain grouping if available,
    else by category/module). Risky files are skipped."""
    branch = _branch(cwd)
    if branch in PROTECTED:
        return False, [f"Refusing to commit to protected branch '{branch}'. Create a feature branch first."]
    safe, risky = _stage_candidates(cwd, stage_all)
    if not safe:
        return False, ["Nothing to commit." + (f" (skipped {len(risky)} risky file(s))" if risky else "")]

    groups: list[tuple[str | None, list[str]]] | None = None
    if msg_mode != "off":
        from backend.app.engines.copilot import brain
        if msg_mode == "llm" or brain.available():
            groups = _brain_groups(cwd, safe)
    if groups is None:
        groups = _heuristic_groups(cwd, safe)

    lines: list[str] = []
    for message, files in groups:
        _git(cwd, "reset", "-q", check=False)
        _git(cwd, "add", "--", *files)
        staged = _git(cwd, "diff", "--cached")
        if not staged.strip():
            continue
        if scan(staged):
            _git(cwd, "reset", "-q", check=False)
            lines.append(f"  BLOCKED (secrets): {', '.join(files)}")
            continue
        if not message:                              # heuristic groups defer the message to here,
            message = auto_message(staged, mode="off")  # so new files get one from the staged diff
        _git(cwd, "commit", "-q", "-m", message)
        head = _git(cwd, "rev-parse", "--short", "HEAD").strip()
        lines.append(f"  {head}  {message}  [{len(files)} file{'s' if len(files) != 1 else ''}]")
    if risky:
        lines.append(_excluded_note(risky).strip())
    return True, lines


# ---- absorb ---------------------------------------------------------------

def _earliest(cwd: str, shas: list[str]) -> str:
    order = [s.strip() for s in _git(cwd, "log", "--format=%H", "-n", "300").splitlines()]
    best, best_idx = shas[0], -1
    for s in shas:
        i = order.index(s) if s in order else -1
        if i > best_idx:
            best_idx, best = i, s
    return best


def absorb(cwd: str, into: str | None = None) -> tuple[bool, str]:
    """Fold working-tree changes into the right earlier commit(s) and re-stack
    (fixup + non-interactive autosquash). Refuses on protected/pushed history."""
    if not _git(cwd, "status", "--porcelain").strip():
        return False, "Nothing to absorb — the working tree is clean."
    branch = _branch(cwd)
    if branch in PROTECTED:
        return False, f"Refusing to absorb on protected branch '{branch}'. Switch to a feature branch first."
    changed = [ln.strip() for ln in _git(cwd, "diff", "HEAD", "--name-only").splitlines() if ln.strip()]
    if not changed:
        return False, "Only new/untracked files — nothing to absorb. Use `gitly commit`."

    try:
        upstream = _git(cwd, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}").strip()
    except GitError:
        upstream = ""
    since = f"{upstream}..HEAD" if upstream else ""

    targets: dict[str, list[str]] = {}
    for f in changed:
        t = into or ""
        if not t:
            args = ["log", "-n", "1", "--format=%H"]
            if since:
                args.append(since)
            args += ["--", f]
            t = _git(cwd, *args).strip()
        if not t:
            return False, f'No local commit found that touches "{f}". Commit it first (`gitly commit`) or pass --into.'
        targets.setdefault(t, []).append(f)

    if upstream:
        for t in targets:
            if _git(cwd, "branch", "-r", "--contains", t, check=False).strip():
                return False, f"Target {t[:8]} is already pushed — refusing to rewrite published history."

    for t, fs in targets.items():
        _git(cwd, "reset", "-q")
        _git(cwd, "add", "--", *fs)
        _git(cwd, "commit", "-q", "--fixup", t)

    earliest = _earliest(cwd, list(targets))
    try:
        _git(cwd, "rev-parse", "--verify", f"{earliest}^")
        base = [f"{earliest}^"]
    except GitError:
        base = ["--root"]
    try:
        _git(cwd, "rebase", "-i", "--autosquash", *base,
             env={"GIT_SEQUENCE_EDITOR": "true", "GIT_EDITOR": "true"})
    except GitError:
        _git(cwd, "rebase", "--abort", check=False)
        return False, "Could not absorb cleanly (rebase conflict). Aborted — commits and changes untouched."

    n = sum(len(v) for v in targets.values())
    return True, f"Absorbed {n} file change(s) into {len(targets)} commit(s): {', '.join(t[:8] for t in targets)}. History re-stacked."
