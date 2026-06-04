"""Secret firewall: catch real secrets, don't cry wolf on ordinary code.

The entropy layer is gated by `_looks_random` (letter + digit) to avoid flagging
identifiers, paths, and dictionary phrases. These tests pin both halves: recall on real
secrets (via patterns and/or entropy) and silence on the false positives that the
entropy detector used to fire on (discovered while committing gitly's own docs).

The secret-bearing lines below carry a `gitly:allow` pragma so this very file can be
committed through gitly — which is also the feature under test."""
from __future__ import annotations

import pytest

from backend.app.security.secret_firewall import is_clean, redact, scan

# Real secrets — every one must be caught (by a pattern, the entropy layer, or both).
REAL_SECRETS = [
    "AKIA1234567890ABCDEF",                     # aws access key id (pattern)  gitly:allow
    "ghp_aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY",  # github token (pattern)       gitly:allow
    "sk-ant-abc123def456ghi789jkl012mno345",    # anthropic (pattern)          gitly:allow
    "AIzaSyabcdefghijklmnopqrstuvwxyz0123456",  # google api key (pattern)     gitly:allow
    "wOeiF8sLkJh3nMq0pXcVbZ2aServerSecret99",   # random blob (entropy)        gitly:allow
]

# False positives — ordinary strings the entropy layer must NOT flag. These are the exact
# tokens that blocked gitly's docs commit before the `_looks_random` gate was added.
FALSE_POSITIVES = [
    "fontawesome/brands/github",          # mkdocs.yml icon config
    "GITLY_PROVENANCE_SYNC=true",         # an env-var assignment in the docs
    "GITLY_SECRET_FAIL_CLOSED",           # a SCREAMING_SNAKE identifier
    "getting-started/installation",       # a docs path / slug
    "/path/to/Gitly/sdk/mcp/dist/index",  # a file path
    "independently-reviewable",           # a long hyphenated word
]


@pytest.mark.parametrize("secret", REAL_SECRETS)
def test_real_secrets_are_caught(secret):
    line = f'value = "{secret}"'  # built at runtime, so the literal carries no pragma
    assert scan(line), f"missed a real secret: {secret!r}"
    assert not is_clean(line)


@pytest.mark.parametrize("token", FALSE_POSITIVES)
def test_false_positives_pass(token):
    assert is_clean(token), f"false positive on bare token: {token!r}"
    assert is_clean(f"  - {token}: something"), f"false positive in context: {token!r}"


def test_entropy_layer_requires_letter_and_digit():
    # A long, high-entropy, letter-only token is treated as a word, not a secret…
    assert is_clean("aBcDeFgHiJkLmNoPqRsTuVwXyZ")
    # …add digits (real key material) and the entropy layer fires.
    assert scan("aB3dE5gH7iJ9kL1mN0pQ2rS4uV6xZ8w")  # gitly:allow


def test_allowlist_pragma_exempts_gate_but_not_redaction():
    secret = "AKIA1234567890ABCDEF"  # bound once, pragma'd  gitly:allow
    line = f"aws = '{secret}'  # gitly:allow"
    # the commit gate (default) honors the pragma → nothing blocks the commit…
    assert scan(line) == []
    assert is_clean(line)
    # …but redaction ignores pragmas, so the secret is still stripped before any LLM call.
    assert secret not in redact(line)
    assert scan(line, honor_allowlist=False), "honor_allowlist=False must still see it"


def test_redaction_replaces_and_is_typed():
    secret = "sk-proj-abcdefghij0123456789ABCDEFGH"  # bound once, pragma'd  gitly:allow
    out = redact(f"OPENAI_API_KEY = '{secret}'")
    assert secret not in out
    assert "‹redacted:" in out


def test_clean_code_stays_clean():
    assert is_clean("def add(a, b):\n    return a + b\n")
    assert is_clean("import os\nfrom pathlib import Path\n")
