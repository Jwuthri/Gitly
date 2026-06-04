# gitly

**Git-quality tooling for the AI-authorship era.** Helps any developer — experienced or "vibe coding" — commit cleanly, ship reviewable PRs, understand diffs, and know who *really* wrote the code. Built to meet developers where they already are: inside their AI coding agent.

> `git blame` tells you who *typed* it. **`gitly trace`** tells you who — or what — actually *wrote* it.

---

## Contents
- [The four pillars](#the-four-pillars)
- [Repository layout](#repository-layout)
- [Architecture](#architecture)
- [Quickstart (Docker)](#quickstart-docker)
- [See it work: seed demo data](#see-it-work-seed-demo-data)
- [The website](#the-website)
- [The `gitly` CLI](#the-gitly-cli)
- [The MCP server (Claude Code / Cursor)](#the-mcp-server-claude-code--cursor)
- [Git hooks](#git-hooks)
- [HTTP API reference](#http-api-reference)
- [Configuration](#configuration)
- [Local development (no Docker)](#local-development-no-docker)
- [Testing](#testing)
- [Security posture](#security-posture)
- [Status & roadmap](#status--roadmap)

---

## The four pillars

```
        AUTHOR        →     STRUCTURE    →      REVIEW
       copilot              shrink              lens
          └──────────────────┬──────────────────┘
                          TRACE
        provenance ground-truth beneath all three
```

| Pillar | What it does | Status |
|---|---|---|
| **copilot** | Commit *correctly* instead of `git add . && git commit -m "wip"`. Safe staging, auto-written conventional messages, semantic `--split`, `absorb`, **secret firewall**. | commit · absorb · split · scan live |
| **shrink** | Turn an unreviewable megaPR into a dependency-ordered stack of small sub-PRs — each compiles & tests — with a *verified* completeness guarantee (`tree(base+slices) == tree(head)`). | **live** (CLI + plan API · verified stacks) |
| **lens** | Re-render a diff as conceptual **change clusters** ("this 47-site rename is one thing") with outlier flagging. | **live** (substitution · insertion · outlier) |
| **trace** | **AI authorship provenance.** Records which model/agent wrote which line, from which (secret-redacted) prompt, how much a human changed it, and whether it was reviewed. | live |

The engines for `shrink` and `lens` port in from two sibling repos — see [`MIGRATION.md`](MIGRATION.md).

---

## Repository layout

```
gitly/
├── backend/         FastAPI API + the four engines            (Python · FastAPI · Celery)
│   └── app/
│       ├── api/routes/   health · trace · lens · copilot · shrink
│       ├── engines/      trace + lens + shrink (real) · copilot (seam)
│       ├── security/     secret_firewall.py  (layered scan + redaction)
│       ├── db/           SQLAlchemy models + session
│       ├── cli.py        the `gitly` CLI
│       ├── celery_app.py Celery app
│       └── main.py       FastAPI app (CORS, lifespan, routers)
├── workers/         Celery tasks (async shrink / provenance sync)
├── shared/          framework-free kernel + Pydantic contracts
│   ├── diff_core/   unified-diff parser (shared by all engines)
│   └── schema/      provenance.py + common.py  (the data contracts)
├── sdk/
│   ├── python/      gitly_sdk — dependency-free provenance recorder
│   ├── mcp/         @gitly/mcp — MCP server for Claude Code / Cursor   (see sdk/mcp/README.md)
│   └── hooks/       pre-commit (secret block) · claude_post_tool.py (capture)
├── frontend/        dashboards & diff viewers                  (Next.js · Postgres)
│   ├── app/         / · /copilot · /shrink · /lens · /trace
│   ├── components/  Nav · ProvenanceTable · AuthorshipBar · LensClient · SecretScanDemo
│   └── lib/         api.ts (SSR) · clientApi.ts (browser) · db.ts (optional direct PG)
├── scripts/         seed_demo.py  (fake provenance for the dashboard)
├── docker/          Dockerfile.backend · Dockerfile.frontend
├── docker-compose.yml · Makefile · .env.example · MIGRATION.md
```

---

## Architecture

- **One shared kernel.** `shrink`, `lens`, and `trace` all stand on `shared/diff_core` (one unified-diff parser) and `shared/schema` (Pydantic contracts) — not three copies. This is the point of consolidation.
- **Backend (FastAPI)** owns the Postgres schema (SQLAlchemy, `create_all` on boot for dev; Alembic is a dependency, prod migrations TBD) and exposes the engines over HTTP.
- **Workers (Celery + Redis)** run heavy/async jobs (shrink, provenance sync). The broker is Redis.
- **Frontend (Next.js)** reads the backend over HTTP. Server components fetch via the internal service URL (`API_URL_INTERNAL`); the browser uses `NEXT_PUBLIC_API_URL`.
- **SDK + hooks + MCP** are how authorship gets *captured* and how the copilot reaches you inside your agent.

Request flow (trace): an agent edit → capture hook → `gitly_sdk`/MCP writes a **redacted** event to `.gitly/provenance/*.jsonl` → (opt-in) sync to Postgres → `gitly trace` / the dashboard join it with `git blame`.

---

## Quickstart (Docker)

```bash
cp .env.example .env
make up            # docker compose: postgres + redis + backend + worker + frontend
```

| Service | Open at | Internal name |
|---|---|---|
| **Web** (Next.js) | http://localhost:3000 | `frontend:3000` |
| **API** (FastAPI) | http://localhost:8000 — docs at **/docs** | `backend:8000` |
| **Postgres** | `localhost:5433` | `postgres:5432` |
| **Redis** | `localhost:6380` | `redis:6379` |

> Postgres/Redis use **non-default host ports (5433/6380)** so gitly coexists with other local stacks. Inside the compose network, containers still use the standard ports.

Stop with `make down`.

---

## See it work: seed demo data

The `trace` dashboard reads from Postgres. Populate it with realistic fake provenance:

```bash
make seed                            # structured demo: real files with per-line authorship
# or a different repo name:
python3 scripts/seed_demo.py --repo my-app
```

Then open **http://localhost:3000/trace?repo=demo-app**. The seeder is stdlib-only, **idempotent** (same `--seed` upserts, no duplicates), and posts through the real `POST /trace/records` ingest path (one record carries a planted key to demonstrate server-side redaction).

---

## The website

Five pages, two with live demos wired to the backend:

| Route | What's there |
|---|---|
| `/` | Hero (code annotated by author) + the author→structure→review pipeline |
| `/copilot` | Capability cards + **live secret-firewall demo** (`POST /copilot/scan`) |
| `/shrink` | megaPR → verified-stack visualization + the completeness guarantee |
| `/lens` | **live diff analyzer** (`POST /lens/analyze`) |
| `/trace` | provenance dashboard: stat cards, authorship bar, by-model bars, records table |

---

## The `gitly` CLI

Installed as a console script by `pip install -e .` (run `make install` first):

```bash
# --- commit correctly (the copilot pillar) ---
gitly commit                 # stage SAFE changes, auto-write a conventional message, commit
gitly commit -a              # also include untracked files (still skips .env / keys / build junk)
gitly commit -m "feat: ..."  # supply your own message instead of generating one
gitly commit --split         # break the working tree into several logical commits (one per concern)
gitly commit --path src/a.py # stage only the path(s) you name
gitly absorb                 # fold uncommitted edits into the earlier commit(s) they belong to (fixup + autosquash)

# --- setup & the "brain" (where messages & splits come from) ---
gitly init                   # install the secret-blocking pre-commit hook (--claude-code adds capture)
gitly auth                   # one-time setup: Claude Code (zero-config) / OpenAI / Anthropic / offline
gitly config                 # show the active provider + key sources (values are never printed)

# --- the rest ---
gitly trace <file>           # per-line AI/human provenance (git blame + recorded provenance)
gitly trace --summary        # repo rollup: % AI, by model, unreviewed-AI lines
gitly scan --staged          # secret firewall over staged changes (exit 1 = blocked)
echo "text" | gitly scan     # scan stdin
gitly shrink <base> <head> --repo .  # split a PR into a VERIFIED stack (materialize + tree-equality)
git diff main | gitly lens         # cluster a diff into conceptual cards (renames / insertions / outliers)
```

**Intelligence, with zero config.** `gitly commit` writes the conventional-commit message for you, and `--split` carves a sprawling working tree into independently-reviewable commits. The "brain" resolves a provider in this order: an explicit one (`GITLY_LLM_PROVIDER` / `gitly auth`) → an `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (real env **or your project's `.env`**) → your local **Claude Code** CLI (`claude -p` — no key at all) → a fully offline heuristic (the lens engine). Run `gitly auth` once to choose; there's nothing to configure if Claude Code is installed.

**It can't leak, and it won't stage the wrong thing.** Every diff is **secret-redacted before it reaches any model** (even your own agent). The **safe-add guard never stages `.env`, `*.pem`/`*.key`, credentials, or build artifacts** (`node_modules/`, `dist/`, `.next/`, …) — and if you force one with `--path`, the **secret firewall** still blocks the commit. Protected branches (`main`/`master`/`develop`/`release`) are refused; published commits are never rewritten by `absorb`.

---

## The MCP server (Claude Code / Cursor)

A pure-Node stdio server in [`sdk/mcp/`](sdk/mcp/README.md) that composes local git + the gitly backend + the provenance ledger into 8 opinionated tools: `gitly_status`, `gitly_scan_secrets`, `gitly_explain_diff`, `gitly_safe_commit`, `gitly_absorb`, `gitly_trace_summary`, `gitly_record_authorship`, `gitly_shrink`.

```bash
cd sdk/mcp && npm install && npm run build      # -> dist/
npm run smoke                                    # optional: verify against a running backend

claude mcp add gitly -- node /absolute/path/to/gitly/sdk/mcp/dist/index.js
```

Then: *"gitly, is this change too big?"* · *"commit this cleanly with gitly"* · *"gitly trace summary"*. Point at a non-default backend with `GITLY_API_URL`. Full details: [`sdk/mcp/README.md`](sdk/mcp/README.md).

---

## Claude Code plugin

The repo root is also a **Claude Code plugin** ([`.claude-plugin/plugin.json`](.claude-plugin/plugin.json)) that bundles the MCP server, slash commands, and the authorship-capture hook in one install (`claude plugin validate` passes):

```bash
cd sdk/mcp && npm run build          # build the bundled MCP server once
claude --plugin-dir /absolute/path/to/gitly     # load the plugin for a session
```

- **Slash commands** ([`commands/`](commands)): `/gitly:commit`, `/gitly:absorb`, `/gitly:scan`, `/gitly:shrink`, `/gitly:lens`, `/gitly:trace`.
- **MCP server**: the 8 tools above, launched from `${CLAUDE_PLUGIN_ROOT}/sdk/mcp/dist`.
- **Hook** ([`hooks/hooks.json`](hooks/hooks.json)): a `PostToolUse(Edit|Write)` hook records AI authorship to the local ledger (feeds `gitly trace`).

---

## Git hooks

In [`sdk/hooks/`](sdk/hooks):

- **`pre-commit`** — blocks a commit if the staged diff contains secrets (uses the `gitly` CLI, with a regex fallback). Install:
  ```bash
  ln -sf ../../sdk/hooks/pre-commit .git/hooks/pre-commit
  ```
- **`claude_post_tool.py`** — a Claude Code `PostToolUse(Edit|Write)` hook that records AI authorship to the local ledger (feeds `gitly trace`). Register it in `.claude/settings.json` (snippet at the top of the file).

---

## HTTP API reference

Base: `http://localhost:8000` · interactive docs at **`/docs`**.

| Method | Path | Body / query | Purpose |
|---|---|---|---|
| GET | `/` | — | service metadata (pillars) |
| GET | `/health` | — | liveness |
| POST | `/lens/analyze` | `{ "diff": "<unified diff>" }` | parse a diff into file/hunk skeleton (clustering pending) |
| POST | `/copilot/scan` | `{ "text": "..." }` | secret firewall → findings + redacted preview |
| GET | `/copilot/capabilities` | — | copilot capability status |
| GET | `/trace/summary` | `?repo=<name>` | authorship rollup (%, by model, unreviewed) |
| GET | `/trace/records` | `?repo=<name>` | provenance records (max 500) |
| POST | `/trace/records` | `[ProvenanceRecord, …]` | ingest bound records (opt-in sync; re-redacts prompts) |
| POST | `/shrink/jobs` | `{ "repo", "base", "head", "max_lines" }` | enqueue a shrink job |

---

## Configuration

Set via `.env` (or environment). See [`.env.example`](.env.example).

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://gitly:gitly@localhost:5433/gitly` | Postgres (host port 5433 for local) |
| `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://localhost:6380/…` | Redis / Celery |
| `GITLY_CORS_ORIGINS` | `http://localhost:3000` | allowed origins (exact) |
| `GITLY_CORS_ORIGIN_REGEX` | `https?://(localhost\|127\.0\.0\.1)(:\d+)?` | allow any localhost port in dev |
| `GITLY_SECRET_SCAN` | `true` | enable the secret firewall |
| `GITLY_SECRET_FAIL_CLOSED` | `true` | block on any finding |
| `GITLY_PROVENANCE_LEDGER` | `.gitly/provenance` | local authorship ledger path |
| `GITLY_PROVENANCE_SYNC` | `false` | opt-in: push bound records to the backend |
| `GITLY_ANTHROPIC_API_KEY` | — | optional LLM features; diffs/prompts redacted first |
| `GITLY_GITHUB_APP_ID` / `_WEBHOOK_SECRET` / `_PRIVATE_KEY_PATH` | — | optional, for hosted shrink |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | browser → backend |
| `API_URL_INTERNAL` | `http://backend:8000` | SSR (in-container) → backend (compose only) |

---

## Local development (no Docker)

Run infra in Docker and the app locally, or everything locally.

```bash
make install        # python venv + deps, and `cd frontend && npm install`
# infra only (or run your own postgres/redis on 5433/6380):
docker compose up -d postgres redis

make api            # FastAPI  → http://localhost:8000  (auto-reload)
make worker         # Celery worker
make web            # Next.js  → http://localhost:3000
```

**Hot reload (Docker):** `backend` and `frontend` bind-mount their source with file-watch polling, so edits apply without rebuilds. Restart `worker` to pick up task changes (`docker compose restart worker`).

---

## Testing

```bash
make test                       # pytest — backend/shared (incl. trace + secret-firewall smoke tests)
cd sdk/mcp && npm run smoke     # MCP server end-to-end (needs backend up)
make fmt                        # ruff --fix
```

---

## Security posture

- **Local-first.** Scanning, clustering, and provenance capture run on your machine. Nothing leaves it unless you opt in (`GITLY_PROVENANCE_SYNC`).
- **gitly must never become the leak.** Any LLM call runs detected secrets through the **redaction guard** first, and is opt-in with your own key. Prompts are redacted *before* they touch disk.
- **Layered secret detection at three gates** — agent (MCP/CLI), pre-commit hook, pre-push — because no single scanner suffices and platform push-protection isn't guaranteed.
- Note: GitHub branch protection does **not** block force-pushes by default — gitly's hooks shouldn't assume it does.

---

## Status & roadmap

**Live & verified:** trace engine (recorder + blame-join + CLI) · **lens clustering engine** (substitution / insertion / outlier layers + partition invariant; **CLI + API**) · **shrink engine** (parse → plan → materialize → tree-equality completeness; CLI + plan API) · **copilot CLI** (`commit` with auto-message + safe-add guard, semantic `--split`, `absorb`, and a zero-config "brain": Claude Code / OpenAI / Anthropic / offline, all secret-redacted) · **`gitly init`** (one-command hook install) · secret firewall (entropy-FP gate + `gitly:allow` allowlist) · FastAPI API + all routes · Celery wiring · Next.js site (5 pages) · seed script · MCP server (8 tools) + Claude Code plugin · provenance SDK + capture hook · **docs site** (Material for MkDocs → GitHub Pages) · **CI** (ruff + pytest, 44 tests).

**Next:**
1. Surface `commit` / `--split` / `absorb` as MCP tools (the CLI is live; mirror it for the agent).
2. Shrink: GitHub-App worker (clone → open stacked PRs) + squash-merge stack reconciliation + the Docker validation sandbox.
3. tree-sitter Layer-1 + LLM Layer-3 naming for lens; GitHub PR-URL ingestion.
4. Distribution: publish `gitly` to PyPI + the MCP server to npm.
