"""Edit-shape analysis for hunks — the primitives Layers 1 & 2 cluster on.

Token-level analyzer (no tree-sitter): reduces a hunk's change to one of two canonical
shapes — **substitution** (1:1 token swaps: rename, type change, import path) or
**insertion** (contiguous token runs added: a param, an `await`). Anything else returns
None and falls through to the stub (high precision by construction).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from ..diff.parser import ParsedHunk
from ..models import DiffLineType

_TOKEN_RE = re.compile(
    r"""
      "(?:[^"\\]|\\.)*"        # double-quoted string
    | '(?:[^'\\]|\\.)*'        # single-quoted string
    | `(?:[^`\\]|\\.)*`        # template/backtick string
    | [A-Za-z_$][A-Za-z0-9_$]* # identifier / keyword
    | \d+(?:\.\d+)?            # number
    | [^\sA-Za-z0-9_$]         # one punctuation char
    """,
    re.VERBOSE,
)

_IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")
_STRING_RE = re.compile(r"^(['\"`]).*\1$", re.DOTALL)


def tokenize(line: str) -> list[str]:
    """Split a line into significant tokens (whitespace dropped)."""
    return _TOKEN_RE.findall(line)


def _substitutable(tok: str) -> bool:
    return bool(_IDENT_RE.match(tok)) or bool(_STRING_RE.match(tok)) or tok.isdigit()


def is_string_token(tok: str) -> bool:
    return bool(_STRING_RE.match(tok))


def _removed_added(hunk: ParsedHunk) -> tuple[list[str], list[str]]:
    rem = [ln.content for ln in hunk.lines if ln.type == DiffLineType.remove]
    add = [ln.content for ln in hunk.lines if ln.type == DiffLineType.add]
    return rem, add


def _line_substitutions(r: str, a: str) -> list[tuple[str, str]] | None:
    tr, ta = tokenize(r), tokenize(a)
    subs: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, tr, ta, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag != "replace" or (i2 - i1) != (j2 - j1):
            return None
        for k in range(i2 - i1):
            old, new = tr[i1 + k], ta[j1 + k]
            if old == new:
                continue
            if not (_substitutable(old) and _substitutable(new)):
                return None
            subs.append((old, new))
    return subs


def _line_insertions(r: str, a: str) -> list[str] | None:
    tr, ta = tokenize(r), tokenize(a)
    runs: list[str] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, tr, ta, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag != "insert":
            return None
        runs.append(" ".join(ta[j1:j2]))
    return runs or None


def hunk_substitution(hunk: ParsedHunk) -> frozenset[tuple[str, str]] | None:
    """Return the hunk's token-substitution set, or None if it is not a clean substitution edit."""
    rem, add = _removed_added(hunk)
    if not rem or len(rem) != len(add):
        return None
    mapping: dict[str, str] = {}
    for r, a in zip(rem, add):
        if r == a:
            continue
        subs = _line_substitutions(r, a)
        if subs is None:
            return None
        for old, new in subs:
            if mapping.get(old, new) != new:
                return None
            mapping[old] = new
    if not mapping:
        return None
    return frozenset(mapping.items())


def hunk_insertion(hunk: ParsedHunk) -> tuple[str, ...] | None:
    """Return the tuple of inserted token-runs, or None if the hunk is not a clean insertion."""
    rem, add = _removed_added(hunk)
    if not rem or len(rem) != len(add):
        return None
    runs: list[str] = []
    changed = False
    for r, a in zip(rem, add):
        if r == a:
            continue
        changed = True
        ins = _line_insertions(r, a)
        if ins is None:
            return None
        runs.extend(ins)
    if not changed or not runs:
        return None
    return tuple(runs)


def pretty_run(run: str) -> str:
    """Tidy a space-joined token run for display (drop tokenizer spaces around punctuation)."""
    run = re.sub(r"\s*\.\s*", ".", run)
    run = re.sub(r"\s+([,;:)\]}>])", r"\1", run)
    run = re.sub(r"([(\[{<])\s+", r"\1", run)
    return run.strip()
