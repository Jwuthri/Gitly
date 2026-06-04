# CLI reference

Every `gitly` command at a glance. Installed as a console script by `pip install -e .`.

```console
$ gitly --help
gitly — git-quality tooling for the AI-authorship era.
```

All commands exit **0** on success and **non-zero** on failure (blocked commit, failed
completeness check, secrets found, …), so they compose in scripts and hooks.

---

## `gitly init`

Set up gitly in the current repo: install the secret-blocking **pre-commit** hook (and,
with `--claude-code`, the authorship-capture hook).

```bash
gitly init [--claude-code] [--force] [--repo PATH]
```

| Flag | Meaning |
|---|---|
| `--claude-code` | Also register the Claude Code `PostToolUse` authorship-capture hook in `.claude/settings.json`. |
| `--force` | Replace an existing **non-gitly** pre-commit hook (backs it up to `pre-commit.bak`). |
| `--repo PATH` | Operate on another repo. |

Idempotent — re-running updates gitly's own hook in place. The installed hook calls
`gitly scan --staged` (with a regex fallback if `gitly` isn't on `PATH`). See
[Git hooks](../integrations/hooks.md).

---

## `gitly commit`

Stage safe files, block on secrets, refuse protected branches, and commit — auto-writing a
conventional message if you don't supply one.

```bash
gitly commit [MESSAGE] [-a] [--path PATH]... [--split] [--llm | --no-llm] [--repo PATH]
```

| Argument / flag | Default | Meaning |
|---|---|---|
| `MESSAGE` | auto | Exact message; omit to generate from the diff. |
| `-a`, `--all` | off | Also stage untracked files (safe-add guard still applies). |
| `--path PATH` | — | Stage only these path(s); repeatable. |
| `--split` | off | Carve the working tree into several logical commits. |
| `--llm` | off | Force the brain to write the message(s). |
| `--no-llm` | off | Never call an LLM; use the offline heuristic. |
| `--repo PATH` | `.` | Operate on another repo. |

Full guide: [Copilot](../pillars/copilot.md).

---

## `gitly absorb`

Fold uncommitted changes into the earlier commit(s) they belong to and re-stack
(fixup + non-interactive autosquash).

```bash
gitly absorb [--into REF] [--repo PATH]
```

| Flag | Default | Meaning |
|---|---|---|
| `--into REF` | auto | Target commit to absorb every change into. |
| `--repo PATH` | `.` | Operate on another repo. |

Refuses protected branches, **won't rewrite pushed commits**, and aborts cleanly on
conflict.

---

## `gitly auth`

Set up the brain (commit messages & splitting). Interactive, or scriptable.

```bash
gitly auth [--provider NAME] [--key KEY] [--show]
```

| Flag | Meaning |
|---|---|
| `--provider` | `claude-code` \| `openai` \| `anthropic` \| `heuristic`. |
| `--key` | API key for `openai`/`anthropic` (omit to be prompted, hidden). |
| `--show` | Print the active brain and exit (same as `gitly config`). |

Stores to `~/.config/gitly/config.json` (`chmod 600`). If a key is already in the
environment/`.env`, nothing is stored.

---

## `gitly config`

Show the active provider and key **sources** — values are never printed.

```bash
gitly config
```

---

## `gitly trace`

AI-authorship provenance, blame-style.

```bash
gitly trace [FILE] [--summary]
```

| Argument / flag | Meaning |
|---|---|
| `FILE` | File to trace, per line. Omit (or add `--summary`) for a repo rollup. |
| `--summary` | Repo rollup: % AI, by model, unreviewed-AI lines. |

Full guide: [Trace](../pillars/trace.md).

---

## `gitly scan`

The secret firewall. Reads stdin, or `--staged` for the staged diff (use it in a
pre-commit hook). Exit **1** if anything is found.

```bash
gitly scan [--staged]
echo "text" | gitly scan
```

---

## `gitly shrink`

Split a range into a verified stack of small slices.

```bash
gitly shrink BASE [HEAD] [--strength S] [--max-lines N] [--write-refs] [--llm] [--repo PATH]
```

| Argument / flag | Default | Meaning |
|---|---|---|
| `BASE` | — *(required)* | Base ref, e.g. `main`. |
| `HEAD` | `HEAD` | Head ref. |
| `--strength` | `balanced` | `gentle` \| `balanced` \| `aggressive`. |
| `--max-lines N` | `0` | Override the line cap (`0` = use `--strength`). |
| `--write-refs` | off | Create `shrink/*` branches per slice. |
| `--llm` | off | LLM labeler for titles/intent (redacted first). |
| `--repo PATH` | `.` | Path to the repo. |

Exits **1** if the completeness check fails. Full guide: [Shrink](../pillars/shrink.md).

---

## `gitly lens`

Cluster a unified diff into conceptual change cards (renames, insertions, outliers).

```bash
gitly lens [FILE] [--sites] [--json]
git diff main | gitly lens          # reads stdin when FILE is omitted or '-'
```

| Argument / flag | Meaning |
|---|---|
| `FILE` | A `.diff` file to analyze. Omit (or pass `-`) to read a diff from stdin. |
| `--sites` | List each cluster's individual change sites (`file:line`). |
| `--json` | Emit the raw `AnalysisResult` as JSON. |

Exits **1** on an unreadable file, empty input, or an unparseable diff. Full guide:
[Lens](../pillars/lens.md).
