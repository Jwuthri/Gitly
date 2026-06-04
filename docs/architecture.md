# Architecture

gitly is a monorepo that consolidates two sibling projects (`pr-shrinker`,
`pr-visual-diff`) and adds the copilot and trace pillars — all standing on **one shared
diff kernel**.

## Repository layout

```
gitly/
├── backend/         FastAPI API + the four engines            (Python · FastAPI · Celery)
│   └── app/
│       ├── api/routes/   health · trace · lens · copilot · shrink
│       ├── engines/      trace · lens · shrink · copilot (commit/absorb/brain)
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
│   ├── mcp/         @gitly/mcp — MCP server for Claude Code / Cursor
│   └── hooks/       pre-commit (secret block) · claude_post_tool.py (capture)
├── frontend/        dashboards & diff viewers                  (Next.js · Postgres)
│   ├── app/         / · /copilot · /shrink · /lens · /trace
│   ├── components/  Nav · ProvenanceTable · AuthorshipBar · LensClient · …
│   └── lib/         api.ts (SSR) · clientApi.ts (browser) · db.ts (optional direct PG)
├── scripts/         seed_demo.py  (fake provenance for the dashboard)
├── docs/            this documentation site (MkDocs)
├── docker/          Dockerfile.backend · Dockerfile.frontend
└── docker-compose.yml · Makefile · mkdocs.yml · .env.example · MIGRATION.md
```

## Principles

- **One shared kernel.** `shrink`, `lens`, and `trace` all stand on `shared/diff_core`
  (one unified-diff parser) and `shared/schema` (Pydantic contracts) — not three copies.
  This is the point of consolidation.
- **The CLI is lean.** `gitly` depends only on `typer`, `pydantic`, `unidiff`, `networkx`.
  The server stack (`fastapi`, `celery`, `sqlalchemy`, …) is an optional `[server]` extra.
- **Backend (FastAPI)** owns the Postgres schema (SQLAlchemy; `create_all` on boot for
  dev, Alembic available for prod) and exposes the engines over HTTP.
- **Workers (Celery + Redis)** run heavy/async jobs (shrink, provenance sync); Redis is the
  broker.
- **Frontend (Next.js)** reads the backend over HTTP — server components via
  `API_URL_INTERNAL`, the browser via `NEXT_PUBLIC_API_URL`.
- **SDK + hooks + MCP** are how authorship gets *captured* and how the copilot reaches you
  inside your agent.

## Two diff parsers, on purpose

- **`shrink`** uses a **strict** parser (`unidiff`) — it must account for every hunk line
  exactly to guarantee `tree(base + slices) == tree(head)`.
- **`lens`** uses a **lenient** hand-rolled parser tuned for messy real-world diffs, where
  forgiving beats exact.

Both sit above the shared `diff_core` skeleton.

## Request flow (trace)

```
agent edit → capture hook → gitly_sdk / MCP writes a REDACTED event
  → .gitly/provenance/*.jsonl → (opt-in) sync to Postgres
  → gitly trace / dashboard join it with `git blame`
```

## Distribution

gitly ships as **both** a terminal CLI (`pip install`, lean deps) **and** an MCP server +
Claude Code plugin + git hooks — so the same engines work from the shell or from inside
your agent. See [Integrations](integrations/mcp.md).
