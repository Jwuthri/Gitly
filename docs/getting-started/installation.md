# Installation

gitly ships in two layers. Most people only need the first.

## The CLI (lean)

The `gitly` command-line tool has a **small dependency footprint** — `typer`, `pydantic`,
`unidiff`, `networkx` — and nothing from the server stack. It's all you need for
`commit`, `absorb`, `split`, `scan`, `trace`, and `shrink`.

=== "From source"

    ```bash
    git clone https://github.com/Jwuthri/Gitly.git
    cd Gitly
    python -m venv .venv && source .venv/bin/activate
    pip install -e .
    gitly --help
    ```

=== "With make"

    ```bash
    make install     # creates .venv, installs the CLI, and runs `npm install` in frontend/
    ```

!!! tip "Requirements"
    Python **3.12+** and a working `git` on your `PATH`. That's it for the CLI.

Verify:

```console
$ gitly --help
Usage: gitly [OPTIONS] COMMAND [ARGS]...
  gitly — git-quality tooling for the AI-authorship era.
```

## The intelligence (optional)

`gitly commit` can write your commit messages and split commits using an LLM. This is
**opt-in and zero-config** — pick whichever applies:

- **Claude Code installed?** Nothing to do. gitly calls `claude -p` locally, no API key.
- **Have an OpenAI / Anthropic key?** Put it in your project's `.env` (gitly auto-loads
  the nearest one) or run `gitly auth` once.
- **Neither?** gitly falls back to a fully offline heuristic (powered by the lens engine).

```bash
gitly auth      # one-time, interactive: pick a provider
gitly config    # confirm what's active (key values are never printed)
```

See [Copilot → The brain](../pillars/copilot.md#the-brain) for the full resolution order.

## The full stack (server + web)

The dashboards, HTTP API, and async workers are optional and run in Docker.

```bash
cp .env.example .env
make up          # docker compose: postgres + redis + backend + worker + frontend
```

| Service | Open at | Internal name |
|---|---|---|
| **Web** (Next.js) | <http://localhost:3000> | `frontend:3000` |
| **API** (FastAPI) | <http://localhost:8000> — docs at **`/docs`** | `backend:8000` |
| **Postgres** | `localhost:5433` | `postgres:5432` |
| **Redis** | `localhost:6380` | `redis:6379` |

!!! note "Non-default ports on purpose"
    Postgres/Redis bind to **5433 / 6380** on the host so gitly coexists with other
    local stacks. Inside the compose network, containers still use 5432 / 6379.

Installing the server deps locally instead of Docker:

```bash
pip install -e ".[server]"     # fastapi, uvicorn, celery, redis, sqlalchemy, …
pip install -e ".[llm]"        # optional: the anthropic SDK
pip install -e ".[dev]"        # pytest + ruff
```

Stop the stack with `make down`. Next: the [Quickstart](quickstart.md).
