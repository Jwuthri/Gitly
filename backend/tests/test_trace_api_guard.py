"""The write-guard on POST/DELETE /trace/records: a no-op with no key configured (local
dev), a hard 401 without the right bearer once GITLY_API_KEY is set."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.app.api.routes import trace as trace_routes


class _Settings:
    def __init__(self, key):
        self.gitly_api_key = key


def test_open_when_no_key_configured(monkeypatch):
    monkeypatch.setattr(trace_routes, "get_settings", lambda: _Settings(None))
    trace_routes.require_write_key(authorization=None)          # no raise


def test_rejects_missing_or_wrong_bearer(monkeypatch):
    monkeypatch.setattr(trace_routes, "get_settings", lambda: _Settings("s3cret"))
    with pytest.raises(HTTPException) as e:
        trace_routes.require_write_key(authorization=None)
    assert e.value.status_code == 401
    with pytest.raises(HTTPException):
        trace_routes.require_write_key(authorization="Bearer wrong")


def test_accepts_the_configured_bearer(monkeypatch):
    monkeypatch.setattr(trace_routes, "get_settings", lambda: _Settings("s3cret"))
    trace_routes.require_write_key(authorization="Bearer s3cret")   # no raise
