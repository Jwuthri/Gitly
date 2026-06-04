"""The gitly 'brain': provider resolution, .env loading, and — most importantly —
that diffs are secret-redacted BEFORE they ever reach a provider."""
from __future__ import annotations

import os

from backend.app.engines.copilot import brain

_ENV_KEYS = ["GITLY_LLM_PROVIDER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITLY_ANTHROPIC_API_KEY"]


def test_provider_resolution_order(monkeypatch):
    monkeypatch.setattr(brain, "_load_dotenv", lambda: None)   # ignore any real .env on the box
    monkeypatch.setattr(brain, "load_config", lambda: {})
    monkeypatch.setattr(brain, "has_claude_code", lambda: False)
    for k in _ENV_KEYS:
        monkeypatch.delenv(k, raising=False)

    assert brain.provider() == "heuristic"                     # nothing available
    monkeypatch.setattr(brain, "has_claude_code", lambda: True)
    assert brain.provider() == "claude-code"                   # local CLI, no key
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-key")         # gitly:allow
    assert brain.provider() == "anthropic"                     # key beats claude-code
    monkeypatch.setenv("OPENAI_API_KEY", "oai-key")            # gitly:allow
    assert brain.provider() == "openai"                        # openai beats anthropic
    monkeypatch.setenv("GITLY_LLM_PROVIDER", "heuristic")
    assert brain.provider() == "heuristic"                     # explicit override wins


def test_available_reflects_provider(monkeypatch):
    monkeypatch.setattr(brain, "provider", lambda: "heuristic")
    assert brain.available() is False
    monkeypatch.setattr(brain, "provider", lambda: "openai")
    assert brain.available() is True


def test_load_dotenv_does_not_override_real_env(monkeypatch, tmp_path):
    monkeypatch.setattr(brain, "_DOTENV_LOADED", False, raising=False)
    (tmp_path / ".env").write_text("OPENAI_API_KEY=from_dotenv\nGITLY_NEW_VAR=hello\n")  # gitly:allow
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "from_real_env")      # gitly:allow
    monkeypatch.delenv("GITLY_NEW_VAR", raising=False)

    brain._load_dotenv()
    assert os.environ["OPENAI_API_KEY"] == "from_real_env"     # setdefault: real env wins
    assert os.environ["GITLY_NEW_VAR"] == "hello"              # but a new var is picked up


def test_complete_redacts_before_send(monkeypatch):
    """The security-critical path: a secret in the prompt must be redacted before the
    provider function is ever called."""
    monkeypatch.setattr(brain, "_load_dotenv", lambda: None)
    monkeypatch.setenv("GITLY_LLM_PROVIDER", "openai")
    captured = {}

    def fake_openai(prompt, system, max_tokens):
        captured["prompt"] = prompt
        return "feat: thing"

    monkeypatch.setattr(brain, "_openai", fake_openai)
    secret = "AKIA1234567890ABCDEF"                            # gitly:allow
    out = brain.complete(f"write a message for this diff containing {secret}")
    assert out == "feat: thing"
    assert secret not in captured["prompt"]                    # never reached the provider raw
    assert "‹redacted" in captured["prompt"]                   # replaced with a typed placeholder


def test_complete_returns_none_without_provider(monkeypatch):
    monkeypatch.setattr(brain, "provider", lambda: "heuristic")
    assert brain.complete("anything") is None
