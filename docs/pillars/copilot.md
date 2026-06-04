# Copilot — commit & absorb

> Commit *correctly* instead of `git add . && git commit -m "wip"`.

The copilot pillar is the part of gitly you'll touch most. It wraps everyday git in three
guardrails — **safe staging**, a **secret firewall**, and **branch protection** — and adds
a zero-config **brain** that writes your commit messages and splits sprawling changes into
reviewable commits.

All of it is local git plumbing. Nothing leaves your machine except, optionally, a
**redacted** diff sent to the model you chose.

---

## `gitly commit`

```bash
gitly commit [MESSAGE] [OPTIONS]
```

What one `gitly commit` does, in order:

1. **Refuses protected branches.** On `main`/`master`/`develop`/`release` it stops and
   tells you to branch first.
2. **Stages only safe files** (see [the safe-add guard](#the-safe-add-guard)).
3. **Scans the staged diff for secrets.** Any finding → the commit is blocked and the
   changes are un-staged again.
4. **Writes a message** if you didn't pass one — via the [brain](#the-brain), or an
   offline heuristic.
5. **Commits**, and prints the short SHA, branch, file count, and message.

```console
$ gitly commit
Committed 829a4b4 on feature (1 file): feat: add RateLimiter class for managing request rates
```

### Options

| Flag | Meaning |
|---|---|
| `MESSAGE` (positional) | Use this exact message; omit to auto-generate from the diff. |
| `-a`, `--all` | Also stage new/untracked files (still runs the safe-add guard). |
| `--path PATH` | Stage only the path(s) you name (repeatable). |
| `--split` | Carve the working tree into several logical commits. |
| `--llm` | Force the brain to write the message(s). |
| `--no-llm` | Never call an LLM — use the offline heuristic. |
| `--repo PATH` | Operate on a repo other than the current directory. |

---

## The safe-add guard

The number-one footgun for AI-assisted developers is `git add .` sweeping up a `.env`, a
private key, or a 200 MB `node_modules`. gitly's staging refuses to do that.

A changed file is treated as **risky** (and skipped, unless you name it explicitly) when it
looks like:

- an **env / secret file** — `.env`, `.env.*`
- a **credential** — `id_rsa`, `id_ed25519`, `credentials`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.keystore`
- a **build/vendor artifact** — `node_modules/`, `dist/`, `build/`, `.next/`, `__pycache__/`, `.venv/`, `vendor/`, …
- noise — `.DS_Store`, `*.log`

It also honors your `.gitignore` (via `git ls-files --exclude-standard`), so anything you
already ignore never even becomes a candidate. Skipped files are reported, not hidden:

```console
$ gitly commit -a
Committed b202c48 on feature (3 files): feat: update package.json, math.js, math.test.js
  ! skipped 2 risky file(s) — add explicitly with --path if intended: .env (looks like
    an env/secret file); node_modules/foo/index.js (build/vendor artifact)
```

!!! danger "Even forcing a secret can't commit it"
    If you really mean to stage a flagged file, pass `--path`. But the **secret firewall**
    still runs on the staged diff — so a `.env` full of keys is blocked anyway:

    ```console
    $ gitly commit --path .env
    Commit BLOCKED — staged changes contain secrets:
      - openai_key (line 7)
      - high_entropy (line 7)
    (changes unstaged) Remove them and retry.
    ```

---

## The brain

When you omit a message (or pass `--llm`), gitly asks a "brain" to write it. The brain is a
tiny, **stdlib-only** abstraction that resolves a provider in this order:

```
explicit (GITLY_LLM_PROVIDER / gitly auth)
  → OPENAI_API_KEY  (real env OR your project's .env)
  → ANTHROPIC_API_KEY
  → local Claude Code  (claude -p — no key at all)
  → offline heuristic  (the lens engine)
```

The practical upshot:

- **Have Claude Code?** It just works, no key, no config.
- **Have a key?** Put it in `.env` — gitly auto-loads the nearest one **without overriding
  real environment variables** — or run `gitly auth`.
- **Have neither / offline?** You still get a sensible `type: subject` message from the
  heuristic.

!!! shield "Redacted before it leaves your machine"
    Whatever the provider, the prompt+diff is run through the **secret firewall's
    `redact()`** first. gitly will not send a key to an LLM, not even to your own agent.

### `gitly auth`

One-time setup. Interactive, or scriptable with flags.

```console
$ gitly auth
gitly brain — how should I write commit messages & splits?

  1. claude-code   (detected)  — zero-config, uses your Claude Code CLI
  2. openai        — needs an API key (sk-…)
  3. anthropic     — needs an API key (sk-ant-…)
  4. heuristic     — fully offline, no LLM

Choose [1-4]: 1
Saved -> active provider: claude-code
```

```bash
gitly auth --provider openai --key sk-...   # non-interactive
gitly auth --provider claude-code           # no key needed
gitly auth --show                           # same as `gitly config`
```

Keys are stored at `~/.config/gitly/config.json` with `chmod 600`. If a key is already in
your environment/`.env`, `gitly auth` uses it and stores **nothing**.

### `gitly config`

Read-only. Shows the active provider and **where** keys come from — never their values.

```console
$ gitly config
active provider : openai
claude code     : available
api keys        : OPENAI_API_KEY (env/.env) (never displayed, never committed)
config file     : ~/.config/gitly/config.json
```

---

## `gitly commit --split`

Semantic auto-splitting: take everything in the working tree and commit it as several
**independently-reviewable** commits instead of one blob.

- With a brain, gitly asks the model to group files into logical commits (one call) — with
  a hard guarantee that **every file lands in exactly one group**, or it falls back.
- Offline, it groups by **category then module** in a sensible order:
  `chore → src → test → docs`.
- Each group is staged on its own, **re-scanned for secrets**, and its message is derived
  from the *staged* diff (so brand-new files get a real message too).

```console
$ gitly commit --split -a
Split into commits:
  69b372f  deps: update Makefile and pyproject.toml for server dependencies  [2 files]
  a739f08  feat: add commit and absorb commands to CLI                       [3 files]
  d4f833d  docs: update README with new features and instructions            [1 file]
  7e2ed37  docker: update backend Dockerfile                                 [1 file]
```

!!! example "gitly committed itself"
    The output above is the real split of this very feature — gitly grouped its own
    `cli.py` + `brain.py` + `ops.py` into one `feat:` commit, dependencies into another,
    and docs and Docker into their own.

---

## `gitly absorb`

You committed, then noticed a one-line fix that *belongs* in an earlier commit. Instead of
a `fix typo` commit, **absorb** it: gitly finds the right target commit per file, creates
fixups, and replays them with a non-interactive autosquash rebase.

```bash
gitly absorb            # auto-target: the most recent commit touching each changed file
gitly absorb --into <ref>   # force a specific target commit
```

```console
$ gitly absorb
Absorbed 1 file change(s) into 1 commit(s): a739f08. History re-stacked.
```

Guardrails:

- Refuses protected branches.
- **Never rewrites pushed history** — if a target commit already exists on the remote,
  absorb stops.
- On a rebase conflict it **aborts cleanly**, leaving your commits and working tree
  untouched.

---

## Cheat sheet

```bash
gitly commit                     # safe stage + auto message + commit
gitly commit -m "fix: …"         # your own message
gitly commit -a                  # include untracked (still skips .env / junk)
gitly commit --path src/a.py     # stage only this
gitly commit --split             # several logical commits
gitly commit --no-llm            # force the offline heuristic
gitly absorb                     # fold edits into the right earlier commit
gitly auth        /  gitly config   # set up / inspect the brain
```
