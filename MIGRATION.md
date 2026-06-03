# Migrating the engines into gitly

`shrink` and `lens` already exist as real, tested engines in two sibling repos. The scaffold leaves typed seams for them; porting is mechanical.

## 1. shrink ← pr-shrinker

Source: `../pr-shrinker/src/prshrink/engine/`  → Target: `backend/app/engines/shrink/`

| Source | Target | Notes |
|---|---|---|
| `engine/diff/parse.py` | `shared/diff_core/parser.py` | **Merge** into the shared kernel (don't duplicate). |
| `engine/diff/materialize.py` | `backend/app/engines/shrink/materialize.py` | The crown jewel — keep as-is. |
| `engine/diff/completeness.py` | `backend/app/engines/shrink/completeness.py` | `tree(base+slices)==tree(head)`. Keep the property test. |
| `engine/graph/`, `engine/planner/` | `backend/app/engines/shrink/{graph,planner}/` | Depends only on `shared`. |
| `api/orchestrator/`, `worker/` | `workers/tasks/shrink.py` | Re-home async run under Celery (was Arq). |
| `tests/engine/` | `backend/tests/` | Port the partition/completeness tests first. |

Swap the queue: pr-shrinker used **Arq**; gitly uses **Celery + Redis**. Only the orchestration entrypoints change; the engine is framework-free.

## 2. lens ← pr-visual-diff

Source: `../pr-visual-diff/backend/app/`  → Target: `backend/app/engines/lens/`

| Source | Target | Notes |
|---|---|---|
| `diff/parser.py` | `shared/diff_core/parser.py` | **Merge** into the shared kernel. |
| `clustering/` (engine, fingerprint, template, outlier) | `backend/app/engines/lens/clustering/` | Keep the partition invariant + tests. |
| `models.py`, `schema/cluster.schema.json` | `shared/schema/` | Co-locate with the shared contracts. |
| `api/routes.py` | `backend/app/api/routes/lens.py` | Re-home `/analyze` onto the gitly router. |
| `frontend/` | `frontend/app/lens/` | Cluster cards + raw toggle become a route. |

## 3. After porting
- Delete the duplicated diff parsers; everything imports `shared.diff_core`.
- Point both engines' Pydantic models at `shared/schema`.
- One `pytest` runs all engine tests; one `docker compose up` runs the whole product.
