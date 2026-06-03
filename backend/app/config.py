from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://gitly:gitly@localhost:5432/gitly"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    gitly_cors_origins: str = "http://localhost:3000"
    # allow any localhost / 127.0.0.1 port in local dev (the browser may be on :3000, :80, etc.)
    gitly_cors_origin_regex: str = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

    gitly_secret_scan: bool = True
    gitly_secret_fail_closed: bool = True

    gitly_provenance_ledger: str = ".gitly/provenance"
    gitly_provenance_sync: bool = False

    gitly_anthropic_api_key: str | None = None

    gitly_github_app_id: str | None = None
    gitly_github_webhook_secret: str | None = None
    gitly_github_private_key_path: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.gitly_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
