"""Symbol analysis: annotate hunks with the symbols they define and reference.

v1 ships a `HeuristicAnalyzer` (regex-based, always available, language-aware by file
extension). It is intentionally a cheap *guess*, not sound name resolution — the
validation sandbox is the real correctness gate. The `Analyzer` protocol lets a
high-fidelity per-language analyzer (tree-sitter, etc.) drop in later.
"""
from __future__ import annotations

import re
from typing import Protocol

from ..diff.models import Diff, Hunk

_EXT_LANG = {
    ".py": "python", ".pyi": "python",
    ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "ts", ".tsx": "ts",
    ".go": "go", ".rs": "rust", ".java": "java", ".rb": "ruby",
}

_DEF_PATTERNS: dict[str, list[re.Pattern]] = {
    "python": [
        re.compile(r"^\s*def\s+([A-Za-z_]\w*)"),
        re.compile(r"^\s*class\s+([A-Za-z_]\w*)"),
        re.compile(r"^\s*([A-Z_][A-Z0-9_]+)\s*="),
    ],
    "js": [
        re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)"),
        re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)"),
        re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*="),
        re.compile(r"\bexport\s+(?:default\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)"),
    ],
    "go": [
        re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)"),
        re.compile(r"\btype\s+([A-Za-z_]\w*)"),
    ],
    "rust": [
        re.compile(r"\bfn\s+([A-Za-z_]\w*)"),
        re.compile(r"\b(?:struct|enum|trait)\s+([A-Za-z_]\w*)"),
    ],
    "java": [
        re.compile(r"\b(?:class|interface|enum)\s+([A-Za-z_]\w*)"),
        re.compile(r"\b(?:public|private|protected)\s+[\w<>\[\]]+\s+([A-Za-z_]\w*)\s*\("),
    ],
    "ruby": [
        re.compile(r"\bdef\s+([A-Za-z_]\w*[!?]?)"),
        re.compile(r"\b(?:class|module)\s+([A-Z]\w*)"),
    ],
}
_DEF_PATTERNS["ts"] = _DEF_PATTERNS["js"] + [
    re.compile(r"\b(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)"),
]

_IMPORT_PATTERNS: dict[str, list[re.Pattern]] = {
    "python": [
        re.compile(r"^\s*from\s+([.\w]+)\s+import"),
        re.compile(r"^\s*import\s+([.\w]+)"),
    ],
    "js": [
        re.compile(r"""\bfrom\s+['"]([^'"]+)['"]"""),
        re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)"""),
    ],
    "go": [re.compile(r"""^\s*"([^"]+)"\s*$""")],
}
_IMPORT_PATTERNS["ts"] = _IMPORT_PATTERNS["js"]

_IDENT = re.compile(r"[A-Za-z_$][\w$]*")
_KEYWORDS = {
    "if", "else", "for", "while", "return", "import", "from", "export", "const", "let",
    "var", "function", "class", "def", "self", "this", "true", "false", "null", "None",
    "True", "False", "and", "or", "not", "in", "is", "new", "async", "await", "type",
    "interface", "enum", "struct", "func", "fn", "public", "private", "protected",
}


def lang_of(path: str) -> str | None:
    for ext, lang in _EXT_LANG.items():
        if path.endswith(ext):
            return lang
    return None


def _added_lines(hunk: Hunk) -> list[str]:
    return [ln[1:] for ln in hunk.text.splitlines() if ln.startswith("+") and not ln.startswith("+++")]


class Analyzer(Protocol):
    def annotate(self, diff: Diff) -> None:
        """Mutate each hunk in-place, filling symbols_defined / symbols_referenced."""
        ...


class HeuristicAnalyzer:
    """Regex-based, dependency-free, always available."""

    def annotate(self, diff: Diff) -> None:
        for f in diff.files:
            lang = lang_of(f.path)
            for hunk in f.hunks:
                added = _added_lines(hunk)
                hunk.symbols_defined = self._defs(lang, added)
                hunk.symbols_referenced = self._refs(lang, added, hunk.symbols_defined)

    def _defs(self, lang: str | None, lines: list[str]) -> list[str]:
        if not lang:
            return []
        out: list[str] = []
        for pat in _DEF_PATTERNS.get(lang, []):
            for ln in lines:
                m = pat.search(ln)
                if m:
                    out.append(m.group(1))
        return sorted(set(out))

    def _refs(self, lang: str | None, lines: list[str], defined: list[str]) -> list[str]:
        defined_set = set(defined)
        refs: set[str] = set()
        for ln in lines:
            for ident in _IDENT.findall(ln):
                if ident in _KEYWORDS or ident in defined_set or len(ident) <= 1:
                    continue
                refs.add(ident)
        return sorted(refs)

    def imports(self, path: str, hunks: list[Hunk]) -> list[str]:
        lang = lang_of(path)
        if not lang:
            return []
        specs: set[str] = set()
        for hunk in hunks:
            for ln in _added_lines(hunk):
                for pat in _IMPORT_PATTERNS.get(lang, []):
                    m = pat.search(ln)
                    if m:
                        specs.add(m.group(1))
        return sorted(specs)
