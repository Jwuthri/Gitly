"""The redaction rule exists in three places (backend firewall, python SDK, TS MCP mirror).
This pins the two python ones to a single fixture file so they can't silently drift; the TS
mirror consumes the same fixtures in sdk/mcp/test/redaction.test.mjs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from backend.app.security.secret_firewall import redact as firewall_redact

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "sdk" / "python"))
from gitly_sdk.provenance import redact as sdk_redact  # noqa: E402

FIXTURES = json.loads((ROOT / "shared" / "redaction_fixtures.json").read_text())["secrets"]


@pytest.mark.parametrize("fx", FIXTURES, ids=[f["name"] for f in FIXTURES])
def test_backend_firewall_masks_every_fixture(fx):
    hidden = fx.get("must_hide", fx["text"])
    assert hidden not in firewall_redact(f"payload with {fx['text']} inside")


@pytest.mark.parametrize("fx", FIXTURES, ids=[f["name"] for f in FIXTURES])
def test_python_sdk_masks_every_fixture(fx):
    hidden = fx.get("must_hide", fx["text"])
    assert hidden not in sdk_redact(f"payload with {fx['text']} inside")
