"""The gitly 'brain' — a tiny LLM abstraction for commit messages + semantic splitting.

Zero-config when **Claude Code** is installed (`claude -p`, no API key). Otherwise an
**OpenAI** or **Anthropic** key, set once via `gitly auth` (or env). Stdlib only
(urllib/subprocess) so the CLI stays lean. Diffs are **secret-redacted before they reach
any provider** — gitly never leaks, even to your own agent.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from backend.app.security.secret_firewall import redact

CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "gitly" / "config.json"

_DOTENV_LOADED = False


def _load_dotenv() -> None:
    """Load the nearest `.env` (cwd upward) WITHOUT overriding real env vars, so a key
    dropped in the project's .env 'just works'. Stdlib only; runs at most once.

    We only read the file into this process's env — gitly's safe-add guard still refuses
    to *stage* a .env, so the key is used but never committed."""
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True
    here = Path.cwd()
    for base in (here, *here.parents):
        f = base / ".env"
        if f.is_file():
            try:
                for raw in f.read_text().splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    k = k.strip()
                    if k.startswith("export "):
                        k = k[len("export "):].strip()
                    os.environ.setdefault(k, v.strip().strip('"').strip("'"))
            except OSError:
                pass
            return  # nearest .env wins


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    try:
        CONFIG_PATH.chmod(0o600)  # it may hold an API key
    except OSError:
        pass


def has_claude_code() -> bool:
    return shutil.which("claude") is not None


def provider() -> str:
    """Active provider: explicit (env/config) > OpenAI key > Anthropic key > Claude Code > heuristic."""
    _load_dotenv()
    if os.environ.get("GITLY_LLM_PROVIDER"):
        return os.environ["GITLY_LLM_PROVIDER"]
    cfg = load_config()
    if cfg.get("provider"):
        return cfg["provider"]
    if os.environ.get("OPENAI_API_KEY") or cfg.get("openai_key"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("GITLY_ANTHROPIC_API_KEY") or cfg.get("anthropic_key"):
        return "anthropic"
    if has_claude_code():
        return "claude-code"
    return "heuristic"


def available() -> bool:
    return provider() != "heuristic"


def complete(prompt: str, *, system: str = "You are a precise, terse git assistant.", max_tokens: int = 600) -> str | None:
    """Return the model's completion, or None if no provider / on any error. The prompt is
    secret-redacted before it leaves the machine."""
    p = provider()
    safe = redact(prompt)
    try:
        if p == "claude-code":
            return _claude_code(safe, system)
        if p == "openai":
            return _openai(safe, system, max_tokens)
        if p == "anthropic":
            return _anthropic(safe, system, max_tokens)
    except Exception:
        return None
    return None


def _claude_code(prompt: str, system: str) -> str | None:
    r = subprocess.run(["claude", "-p", f"{system}\n\n{prompt}"], capture_output=True, text=True, timeout=120)
    out = (r.stdout or "").strip()
    return out or None if r.returncode == 0 else None


def _cfg_key(env: str, field: str) -> str | None:
    return os.environ.get(env) or load_config().get(field)


def _openai(prompt: str, system: str, max_tokens: int) -> str | None:
    key = _cfg_key("OPENAI_API_KEY", "openai_key")
    if not key:
        return None
    body = json.dumps({
        "model": os.environ.get("GITLY_OPENAI_MODEL", "gpt-4o-mini"),
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    return (d["choices"][0]["message"]["content"] or "").strip() or None


def _anthropic(prompt: str, system: str, max_tokens: int) -> str | None:
    key = _cfg_key("ANTHROPIC_API_KEY", "anthropic_key") or os.environ.get("GITLY_ANTHROPIC_API_KEY")
    if not key:
        return None
    body = json.dumps({
        "model": os.environ.get("GITLY_ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        "max_tokens": max_tokens, "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        d = json.loads(r.read())
    return ("".join(b.get("text", "") for b in d.get("content", []))).strip() or None
