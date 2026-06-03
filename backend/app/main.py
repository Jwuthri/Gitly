from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.app.api.routes import copilot, health, lens, shrink, trace
from backend.app.config import get_settings
from backend.app.db import models  # noqa: F401  (register ORM models on Base.metadata)
from backend.app.db.session import Base, engine

settings = get_settings()


def _wait_for_db(max_attempts: int = 60, delay: float = 2.0) -> None:
    """Wait for Postgres to be reachable before creating tables. Survives startup
    ordering races (e.g. an orchestrator that doesn't honor depends_on health gates)
    and transient DNS/connection failures — instead of crashing the container."""
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # OperationalError, DNS EAI_NONAME, conn refused, etc.
            last_err = exc
            print(f"[gitly] waiting for database… ({attempt}/{max_attempts})", flush=True)
            time.sleep(delay)
    raise RuntimeError(f"database unreachable after {max_attempts} attempts") from last_err


@asynccontextmanager
async def lifespan(app: FastAPI):
    _wait_for_db()
    # dev convenience: create tables on boot. Production uses Alembic migrations.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="gitly", version="0.0.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.gitly_cors_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(trace.router)
app.include_router(shrink.router)
app.include_router(lens.router)
app.include_router(copilot.router)


@app.get("/")
def root():
    return {"name": "gitly", "pillars": ["copilot", "shrink", "lens", "trace"]}
