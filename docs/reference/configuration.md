# Configuration

The **CLI needs no configuration**. These variables apply to the optional server/worker
stack and the optional LLM features. Set them via `.env` (auto-loaded) or the environment;
see `.env.example`.

## Server & infrastructure

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://gitly:gitly@localhost:5433/gitly` | Postgres (host port **5433** locally). |
| `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://localhost:6380/…` | Redis / Celery (host port **6380**). |
| `GITLY_CORS_ORIGINS` | `http://localhost:3000` | Allowed origins (exact match). |
| `GITLY_CORS_ORIGIN_REGEX` | `https?://(localhost\|127\.0\.0\.1)(:\d+)?` | Allow any localhost port in dev. |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Browser → backend. |
| `API_URL_INTERNAL` | `http://backend:8000` | SSR (in-container) → backend (compose only). |

## Security & provenance

| Variable | Default | Notes |
|---|---|---|
| `GITLY_SECRET_SCAN` | `true` | Enable the secret firewall. |
| `GITLY_SECRET_FAIL_CLOSED` | `true` | Block on any finding. |
| `GITLY_PROVENANCE_LEDGER` | `.gitly/provenance` | Local authorship ledger path. |
| `GITLY_PROVENANCE_SYNC` | `false` | Opt-in: push bound records to the backend. |

## The brain (LLM features)

All optional. Diffs/prompts are **redacted before any of these are used**.

| Variable | Notes |
|---|---|
| `GITLY_LLM_PROVIDER` | Force a provider: `claude-code` \| `openai` \| `anthropic` \| `heuristic`. |
| `OPENAI_API_KEY` | Enables the OpenAI provider (read from real env **or your project `.env`**). |
| `GITLY_OPENAI_MODEL` | Override the OpenAI model (default `gpt-4o-mini`). |
| `ANTHROPIC_API_KEY` / `GITLY_ANTHROPIC_API_KEY` | Enables the Anthropic provider. |
| `GITLY_ANTHROPIC_MODEL` | Override the Anthropic model. |

Provider resolution order, and how `.env` auto-loading works, are documented under
[Copilot → The brain](../pillars/copilot.md#the-brain). The brain config (provider + any
stored keys) lives at `~/.config/gitly/config.json` with `chmod 600`; set it with
`gitly auth`.

## Hosted shrink (optional)

| Variable | Notes |
|---|---|
| `GITLY_GITHUB_APP_ID` / `_WEBHOOK_SECRET` / `_PRIVATE_KEY_PATH` | For a hosted GitHub-App shrink flow (roadmap). |

!!! warning "Precedence"
    A real environment variable always wins over a value in `.env` — gitly's `.env` loader
    uses `setdefault`, so it never overrides something you've explicitly exported.
