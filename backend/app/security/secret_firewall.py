"""Secret firewall — layered detection + redaction.

No single scanner suffices (ESEM 2023, arXiv:2307.00714: best precision ~75%, best
recall ~88%), so we combine high-recall regex patterns with a Shannon-entropy check.
Used at three gates — agent (pre-commit MCP tool), local pre-commit hook, pre-push
hook — and to redact prompts/diffs before any optional LLM call, so gitly itself
never becomes the leak.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key_id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "aws_secret_access_key": re.compile(r"(?i)aws_secret\w*.{0,20}[:=]\s*['\"]?([A-Za-z0-9/+=]{40})"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
    "slack_token": re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
    "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "generic_assignment": re.compile(
        r"(?i)(?:api[_-]?key|secret|token|passwd|password)\s*[:=]\s*['\"]([^'\"]{12,})['\"]"
    ),
}

_HIGH_ENTROPY_TOKEN = re.compile(r"[A-Za-z0-9+/=_\-]{24,}")


def _looks_random(tok: str) -> bool:
    """A heuristic gate for the entropy layer: real secret material (keys, tokens, hashes)
    mixes **letters and digits**. Identifiers, file paths, and dictionary phrases —
    ``fontawesome/brands/github``, ``GITLY_PROVENANCE_SYNC``, ``getting-started/installation``
    — usually don't, yet are long enough to clear the entropy bar and fire as false
    positives. Requiring both classes removes the bulk of those FPs; the precise
    ``PATTERNS`` layer below still catches known secret formats regardless of this gate."""
    return any(c.isalpha() for c in tok) and any(c.isdigit() for c in tok)


@dataclass(frozen=True)
class Finding:
    kind: str
    line_no: int
    match: str


def _shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in (s.count(ch) for ch in set(s)))


# Inline allowlist — like `# gitleaks:allow` / `# pragma: allowlist secret`. A line carrying
# this marker is exempt from the commit gate (test fixtures, docs that show example keys).
_ALLOW_MARKER = re.compile(r"(?i)gitly[:\-]allow\b|pragma:\s*allowlist\s+secret")


def scan(text: str, *, entropy_threshold: float = 4.0, honor_allowlist: bool = True) -> list[Finding]:
    """Return secret findings. ``honor_allowlist`` (default) skips lines marked with an
    allowlist pragma — used by the *commit gate*. Redaction passes ``honor_allowlist=False``
    so secrets are stripped before any LLM call regardless of pragmas (never-leak wins)."""
    findings: list[Finding] = []
    seen: set[tuple[int, str]] = set()
    for i, line in enumerate(text.splitlines(), start=1):
        if honor_allowlist and _ALLOW_MARKER.search(line):
            continue
        for kind, pat in PATTERNS.items():
            for m in pat.finditer(line):
                key = (i, m.group(0))
                if key not in seen:
                    seen.add(key)
                    findings.append(Finding(kind=kind, line_no=i, match=m.group(0)))
        # entropy layer — catch high-entropy blobs the patterns miss
        for tok in _HIGH_ENTROPY_TOKEN.findall(line):
            key = (i, tok)
            if key in seen or not _looks_random(tok):
                continue
            if _shannon_entropy(tok) >= entropy_threshold:
                seen.add(key)
                findings.append(Finding(kind="high_entropy", line_no=i, match=tok))
    return findings


def redact(text: str) -> str:
    """Replace every detected secret with a typed placeholder. Call before any LLM
    request or before persisting a prompt/diff."""
    out = text
    for f in scan(text, honor_allowlist=False):  # redact everything, pragmas notwithstanding
        out = out.replace(f.match, f"‹redacted:{f.kind}›")
    return out


def is_clean(text: str) -> bool:
    return not scan(text)
