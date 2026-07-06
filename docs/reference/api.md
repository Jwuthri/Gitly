# HTTP API reference

The backend (FastAPI) exposes the engines over HTTP. It's **optional** — the CLI needs
none of it — but it powers the web dashboards and lets your agent reach the engines.

**Base:** `http://localhost:8000` · interactive docs at **`/docs`** (Swagger UI).

| Method | Path | Body / query | Purpose |
|---|---|---|---|
| `GET` | `/` | — | Service metadata (the four pillars). |
| `GET` | `/health` | — | Liveness. |
| `POST` | `/lens/analyze` | `{ "diff": "<unified diff>" }` | Cluster a diff into conceptual cards. |
| `POST` | `/copilot/scan` | `{ "text": "..." }` | Secret firewall → findings + redacted preview. |
| `GET` | `/copilot/capabilities` | — | Copilot capability status. |
| `POST` | `/shrink/analyze` | `{ "diff", "strength" }` | Plan a stack from a diff (400 on a bad diff). |
| `POST` | `/shrink/jobs` | `{ "repo", "base", "head", "max_lines" }` | Enqueue an async shrink — the worker runs the real engine on a repo path it can reach. |
| `GET` | `/trace/summary` | `?repo=<name>` | Authorship rollup (%, by model, unreviewed). |
| `GET` | `/trace/records` | `?repo=<name>&limit=500&offset=0` | Provenance records (paginated, ≤2000/page). |
| `POST` | `/trace/records` | `[ProvenanceRecord, …]` | Ingest records (opt-in sync; **re-redacts** prompts; ≤5000/request). |
| `DELETE` | `/trace/records` | `?repo=<name>` | Clear a repo key's records (`gitly sync --reset`). |

!!! shield "Write guard"
    Set `GITLY_API_KEY` on the backend and `POST`/`DELETE /trace/records` require
    `Authorization: Bearer <key>` (the CLI's `gitly sync` sends it from the same env var).
    Unset, the API stays open for the localhost-only dev loop.

## Examples

=== "Scan for secrets"

    ```bash
    curl -s localhost:8000/copilot/scan \
      -H 'content-type: application/json' \
      -d '{"text": "OPENAI_API_KEY=sk-proj-REDACTED-EXAMPLE"}'
    ```

    Returns the findings and a redacted preview — the response never echoes the raw secret.

=== "Analyze a diff (lens)"

    ```bash
    curl -s localhost:8000/lens/analyze \
      -H 'content-type: application/json' \
      -d '{"diff": "<unified diff>"}'
    ```

=== "Plan a shrink"

    ```bash
    curl -s localhost:8000/shrink/analyze \
      -H 'content-type: application/json' \
      -d '{"diff": "<unified diff>", "strength": "balanced"}'
    ```

=== "Authorship summary"

    ```bash
    curl -s "localhost:8000/trace/summary?repo=demo-app"
    ```

!!! shield "Ingest re-redacts"
    `POST /trace/records` runs every prompt through the secret firewall again on the way
    in, so even a record built by a misbehaving client can't persist a secret. See
    [Security](../security.md).

The request/response models are Pydantic contracts from `shared/schema` — browse them
live at `/docs`.
