# 🧬 gitly — The Complete Guide

> **Git-quality tooling for the AI-authorship era.**
> Helps anyone — pro or "vibe coder" — commit cleanly, ship reviewable PRs, understand diffs, and know who *really* wrote the code.

> 🧒 **ELI5:** People now write tons of code *with AI*, but most never learned git properly. So we get giant unreviewable PRs, `"wip"` commit messages, accidentally-committed passwords, and no idea which lines the AI wrote. **gitly is a friendly git co-pilot that fixes all four** — and it works from your terminal *and* from inside your AI agent (Claude Code, Cursor).

---

## 🗺️ TL;DR (read this first)

gitly is **one toolchain with four "pillars,"** all standing on a shared diff engine and a secret firewall:

| Pillar | Emoji | One line | Status |
|---|---|---|---|
| **Copilot** | ✍️ | Commit *correctly* instead of `git add . && commit -m "wip"` | ✅ Live (CLI) |
| **Shrink** | ✂️ | Turn a megaPR into a *verified* stack of small PRs | ✅ Live (CLI + plan API) |
| **Lens** | 🔍 | Re-read a diff as a few *concepts*, not 600 lines | ✅ Live (CLI + API) |
| **Trace** | 🧬 | Record who/what *actually* wrote each line | ✅ Live (local) · 🟡 sync partial |

> 🔒 **The golden rule:** *gitly must never become the leak.* Secrets are redacted **before** anything reaches an LLM or disk, and blocked at every commit. This is enforced in code, not hoped for.

**Where it runs:** a lean `gitly` CLI (4 dependencies), an MCP server (8 tools), a Claude Code plugin, git hooks, plus an optional web dashboard + API. **44 tests, CI green, docs auto-published.**

---

## 🎯 Why gitly exists

The world changed: people **vibe-code** with agents but never learned git. The symptoms:

- 🐘 **Unreviewable megaPRs** — nobody reviews 1,500 lines; they rubber-stamp.
- 💬 **`"wip"` commit messages** — no history you can actually read.
- 🔑 **Leaked secrets** — `git add .` sweeps up a `.env` or an API key.
- 👻 **No provenance** — `git blame` credits whoever pressed *Enter*, hiding the AI.

gitly fixes the **workflow**, not just the symptoms — and meets you where you already are (the terminal and your agent).

---

## ✍️ Pillar 1 — Copilot (commit & absorb)

> 🧒 **ELI5:** Instead of dumping every change into one messy commit, gitly stages only the *safe* files, writes a clear message for you, blocks secrets, and can even split a big mess into tidy commits — or tuck a small fix into the commit it belongs to.

### What it does
- **`gitly commit`** — stages safe files, writes a conventional message, blocks secrets, refuses protected branches.
- **`gitly commit --split`** — carves a sprawling working tree into several logical commits (one per concern).
- **`gitly absorb`** — folds a follow-up edit into the *earlier* commit it belongs to (no more `"fix typo"` noise).
- **`gitly auth` / `gitly config`** — set up & inspect the "brain" (see below).
- **`gitly init`** — installs the secret-blocking git hook into any repo in one command.

### 🛡️ The safe-add guard (so you never `git add` the wrong thing)
A changed file is treated as **risky** and skipped (unless you name it with `--path`) when it looks like:
- an **env/secret file** — `.env`, `.env.*`
- a **credential** — `id_rsa`, `*.pem`, `*.key`, `*.p12`, `credentials`
- **build/vendor junk** — `node_modules/`, `dist/`, `.next/`, `__pycache__/`, `.venv/`, …

It also respects your `.gitignore`. And if you *force* a flagged file with `--path`, the **secret firewall still blocks the commit**. Belt *and* suspenders.

### 🧠 The "brain" (zero-config intelligence)
When you omit a commit message (or use `--split`), gitly asks an LLM to write it — resolving a provider in this order:

```
explicit (GITLY_LLM_PROVIDER / gitly auth)
  → OPENAI_API_KEY      (real env OR your project's .env)
  → ANTHROPIC_API_KEY
  → local Claude Code   (claude -p — no key at all!)
  → offline heuristic   (powered by the lens engine)
```

> 🔒 Whatever the provider, the diff is **secret-redacted before it leaves your machine** — even to your own agent. Keys live in `~/.config/gitly/config.json` (`chmod 600`) and are **never printed**.

### 🧩 Smart details
- `--split` derives each commit's message from the *staged* diff, so brand-new files still get a real message (a bug we found & fixed while dogfooding).
- `_diff_vs_head` lets the LLM splitter "see" untracked files' content (git diff normally hides them).
- `absorb` **refuses to rewrite pushed history** and aborts cleanly on conflict.

---

## ✂️ Pillar 2 — Shrink (split big PRs)

> 🧒 **ELI5:** Got a giant change that's painful to review? Shrink chops it into a few small, logically-grouped pieces stacked on top of each other — then *mathematically proves* that stacking them all back up gives you **exactly** the original. Nothing added, nothing lost.

### How it works — `parse → plan → materialize → verify`
1. **Parse** 📥 — runs `git diff` against the *merge-base* and parses it with the strict `unidiff` library into files & hunks. (Using the merge-base is what makes the proof hold "by construction.")
2. **Plan** 🧮 — classifies each change (`DEPS → CONFIG → MIGRATION → SOURCE → TEST → DOCS`), groups by module, and orders dependencies with a `networkx` topological sort, then enforces size bounds.
3. **Materialize** 🏗️ — builds a real chain of git commits via plumbing (`read-tree` → `apply --cached` → `write-tree` → `commit-tree`), never touching your working tree.
4. **Verify** ✅ — the crown jewel: checks `tree(base + slices) == tree(head)` by **exact git tree-ID equality**. If it doesn't match, the stack is **not shipped**.

### 🎚️ Strength presets
| `--strength` | max lines/slice | min lines | max slices |
|---|---|---|---|
| `gentle` | 1500 | 300 | 2 |
| `balanced` *(default)* | 400 | 40 | 6 |
| `aggressive` | 120 | 1 | 20 |

> 💡 **Why it's trustworthy:** completeness is proven by tree-ID, *not* by the grouping being smart. A mediocre grouping yields awkward-but-correct PRs — never a broken or lossy stack. The LLM labeler can only touch titles, never which hunks go where.

**Surfaces:** `gitly shrink <base> <head>` (full materialize + verify) · `POST /shrink/analyze` (plan-only, no repo needed).

---

## 🔍 Pillar 3 — Lens (read diffs)

> 🧒 **ELI5:** If a change renames `getUser` → `fetchUser` in 47 places, GitHub shows you 47 diffs. Lens groups all 47 into **one card** ("this is a rename") so you read the *idea*, not the noise — and it points out the 3 spots that *almost* match but quietly differ.

### How it works — layered clustering
| Layer | Detects | Confidence |
|---|---|---|
| **1 · Substitution** | renames, type swaps, import migrations | 🟢 high |
| **2 · Insertion-template** | added params, `await` wrappers, boilerplate | 🟡 medium |
| **Stub** (always last) | claims everything left, one hunk = one card | ⚪ low |
| **Outlier seam** | flags sites that deviate from a cluster's dominant pattern | — |

> 🧮 **Partition invariant:** every hunk lands in **exactly one** cluster — none double-counted, none dropped. This is what makes "47 changes → 1 concept" trustworthy, and it's asserted before any result ships.

**Details:** uses its own *lenient* hand-rolled diff parser (forgiving of messy real-world diffs — unlike shrink's strict one). Results are content-addressed for caching. The same engine powers `gitly lens`, the `/lens` web page, the API, **and** the offline commit-message heuristic.

```console
$ git diff main | gitly lens --sites
  2 files  +2/-2  2 hunks  ->  1 clusters
  ● rename: Renamed `old_name` → `new_name`   [2 sites / 2 files]  (high)
        · a.py:1
        · b.py:1
```

---

## 🧬 Pillar 4 — Trace (AI authorship provenance)

> 🧒 **ELI5:** `git blame` only tells you who *typed* it — which hides the AI behind the keyboard. Trace records the real story the moment an agent edits code (which model, from what prompt, how much a human changed it) and shows it back to you line-by-line.

### How it works
```
agent edit → capture hook → REDACTED event → local ledger (.gitly/provenance/*.jsonl)
   → (opt-in) Postgres sync → join with `git blame` → gitly trace / dashboard
```
- A Claude Code **`PostToolUse` hook** records each edit (model, agent, a *redacted* prompt) to a local, append-only ledger.
- `gitly trace <file>` joins that ledger with `git blame` to tag each line; with no recorded data it *infers* AI authorship from commit trailers (marked `~`, lower confidence).
- `gitly trace --summary` → repo rollup: % AI, by model, and **unreviewed-AI lines** (the metric that tells you where to focus review).

### Data model (the contract)
- **`AuthorType`**: `human` · `ai` · `hybrid` (AI-written, materially human-edited)
- **`AgentKind`**: `claude_code` · `cursor` · `copilot` · `windsurf` · `aider` · `openai_codex` · `antigravity` · `amazon_q` · `lovable` · `gemini` · `continue` · `cody` · `devin` · `replit` · `tabnine` · `jetbrains_ai` · `unknown`
- **`human_edit_ratio`**: 0.0 (untouched AI) → 1.0 (fully rewritten); ≥ 0.5 flips a line to `hybrid`

> 🔒 Prompts are redacted **before they touch disk**, and re-redacted again on server ingest. Two gates, because a provenance record is the one place a prompt could otherwise leak.

---

## 🔒 The Secret Firewall (cross-cutting)

> 🧒 **ELI5:** A bouncer that checks every change for things that look like passwords/keys and refuses to let them into git — and blurs them out before any AI ever sees them.

- **Layered detection:** high-recall regex (AWS, GitHub, OpenAI, Anthropic, Google, Slack, JWT, private keys) **+** a Shannon-entropy check for unknown high-entropy blobs.
- **Three gates:** the agent (MCP/CLI), the pre-commit hook, and the pre-push hook.
- **Redaction:** before any LLM call or on-disk prompt, secrets become typed placeholders like `‹redacted:openai_key›`.

### Two upgrades we made by *dogfooding gitly on itself* 🐶
1. **Fewer false alarms** — the entropy check now requires a token to have **both letters and digits** (real key material does; words/paths/identifiers like `fontawesome/brands/github` don't). We measured the data first to confirm it separates cleanly.
2. **`gitly:allow` pragma** — an inline allowlist (like `# gitleaks:allow`) so test fixtures & docs *can* contain example secrets. The twist: **`redact()` ignores the pragma**, so even an allowlisted line is stripped before any LLM call. Never-leak wins.

---

## 🖥️ The surfaces — how you actually use it

### 1) The `gitly` CLI
| Command | What it does |
|---|---|
| `gitly init` | Install the secret-blocking pre-commit hook (`--claude-code` adds capture) |
| `gitly commit [-m] [-a] [--path] [--split] [--llm/--no-llm]` | Commit cleanly |
| `gitly absorb [--into]` | Fold edits into the right earlier commit |
| `gitly auth` / `gitly config` | Set up / inspect the brain |
| `gitly trace <file>` / `--summary` | Per-line / repo provenance |
| `gitly scan --staged` | Secret firewall (exit 1 = blocked) |
| `gitly shrink <base> <head>` | Verified stack of small PRs |
| `gitly lens [file] [--sites] [--json]` | Cluster a diff into concept cards |

### 2) The MCP server (8 tools, for your agent)
`gitly_status` · `gitly_scan_secrets` · `gitly_explain_diff` · `gitly_safe_commit` · `gitly_absorb` · `gitly_trace_summary` · `gitly_record_authorship` · `gitly_shrink`

### 3) The Claude Code plugin
Bundles the MCP server + **6 slash commands** (`/commit`, `/absorb`, `/scan`, `/lens`, `/shrink`, `/trace`) + the authorship-capture hook — one install (`claude --plugin-dir .`).

### 4) The web dashboard + API (optional)
Next.js site with live demos: `/copilot` (secret scan), `/shrink` (stack preview), `/lens` (diff analyzer), `/trace` (a clickable file-tree + git-blame-style authorship view). FastAPI backend exposes `/lens/analyze`, `/shrink/analyze`, `/copilot/scan`, `/trace/*`.

### 5) The docs site 📚
[Material for MkDocs → GitHub Pages](https://jwuthri.github.io/Gitly/), auto-deployed on every docs change to `master`.

---

## 🏗️ Architecture (the smart bones)

> 🧒 **ELI5:** All four pillars share one "read a diff" engine and one "data shapes" library, so there's no copy-paste. The everyday CLI is tiny; the heavy server stuff is optional.

- **One shared kernel** — `shared/diff_core` (diff parser) + `shared/schema` (Pydantic contracts). Not three copies.
- **Lean CLI** — `gitly` needs only `typer`, `pydantic`, `unidiff`, `networkx`. The server stack (FastAPI, Celery, Postgres…) is an optional `[server]` extra. *CI runs on the lean install as living proof.*
- **Two diff parsers on purpose** — shrink uses a **strict** parser (must account for every line to guarantee the proof); lens uses a **lenient** one (forgiving of messy diffs).
- **Local-first** — everything core runs offline; the DB, web, and any LLM call are opt-in.
- **Repo layout:** `backend/` (engines + API + CLI) · `workers/` (Celery) · `shared/` (kernel) · `sdk/` (python recorder, MCP server, hooks) · `frontend/` (Next.js) · `docs/` (this site).

---

## 🧪 Quality & the dogfooding story

- **44 automated tests** (was 8 at the start of this push), **ruff clean**, **CI** runs both on every PR.
- gitly is **built with gitly**: the commits in this project were made by `gitly commit` / `--split`, which is exactly how we discovered (and fixed) the entropy false-positives, the allowlist gap, the empty-message-for-new-files bug, the `git commit -m` UX trap, and a raw-traceback-on-ignored-file bug. *Using the product is the best test of the product.*

---

## 🧭 Key decisions (and the "why")

| Decision | Why |
|---|---|
| 🔒 **Never leak secrets** (redact before LLM/disk; block at commit) | The #1 risk for AI-assisted devs; trust is the whole product |
| 🧮 **Correctness by tree-ID equality** (shrink) | "Vibes" aren't good enough for rewriting someone's history |
| 🪶 **Lean core deps** + server as an extra | The CLI must be trivial to install; agents shouldn't need Postgres |
| 🤝 **Meet people inside their agent** (MCP + plugin) | That's where vibe-coders already are |
| 🏠 **Local-first, opt-in cloud** | Privacy + works offline |
| 🔁 **Reversed "no new CLI"** → shipped a real CLI | Users wanted `gitly absorb` straight from the terminal |
| 🐶 **Dogfood everything** | The product's own commits are its toughest test |

---

## 🛣️ What's next (the roadmap)

### ✅ Just shipped (Tier 1 + early Tier 2)
Intelligent CLI + brain · docs site · CI + 44 tests · secret-firewall hardening · `gitly lens` CLI · `gitly init`.

### 🔜 Tier 2 — finish parity & polish
- [ ] **MCP parity** — add a `gitly_split` tool (MCP has commit & absorb, but not `--split` yet); surface `lens`/`init` to the agent too.

### 🌱 Tier 3 — the product frontier
- [ ] **Shrink, hosted** — the `run_shrink` Celery task is currently a **no-op**; port the engine into the worker so a GitHub App can clone a repo and open *real* stacked PRs.
- [ ] **Validation sandbox** — compile/test each slice in Docker, upgrading the guarantee from "tree-equality" to "every slice is green."
- [ ] **Close the trace loop** — `bind_to_commit` (which computes `human_edit_ratio` and the `hybrid` flag) exists but **isn't wired to a post-commit hook yet**, so locally those always show defaults. Wiring it makes `gitly trace` fully truthful offline. Then add PR-URL ingestion + a review workflow.
- [ ] **Smarter lens** — tree-sitter (language-aware) Layer 1 + LLM cluster naming; collapse generated files; emit the 6 currently-unused `ClusterKind`s.

### 🚀 Tier 4 — distribution
- [ ] Publish `gitly` to **PyPI** and the MCP server to **npm** (`pip install gitly`, `npx @gitly/mcp`).
- [ ] A demo GIF / landing hero for the docs.

---

## 🐛 Honest known-gaps (found while writing this doc)

> Surfacing these *is* the value of a deep audit — they're the highest-signal next tasks.

1. **`bind_to_commit` isn't wired** → local `gitly trace` can't show real `reviewed` / `human_edit_ratio` (only the DB path can). *(Tier 3)*
2. **`run_shrink` worker is a no-op** → hosted shrink jobs enqueue but do nothing. *(Tier 3)*
3. **Two redaction implementations** — the dependency-free SDK has a *weaker* pattern set than the backend firewall; a local ledger only ever sees SDK-strength redaction (backend re-redacts on ingest). Consider generating one from the other.
4. **Version skew** — the Claude plugin is `0.1.0` while everything else is `0.0.1`.
5. **CI/docs workflows trigger on `master`** (the repo's default) — just be consistent about the branch name in docs.
6. **Partition invariant uses `assert`** — running Python with `-O` would strip the final safety check. Consider a hard `raise`.
7. **Frontend `Nav` hardcodes `localhost:8000/docs`** — wrong in any non-local deploy.
8. **Dead code:** `ProvenanceTable.tsx`, `getTraceRecords`, and the direct-Postgres `db.ts` path are defined but unused.

---

> 💚 **The one-sentence pitch:** gitly turns "I let an AI write it and YOLO-committed" into clean commits, reviewable PRs, readable diffs, and an honest record of who wrote what — without ever leaking a secret.
