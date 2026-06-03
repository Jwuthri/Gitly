"""Language detection + generated-file heuristics. Maps a file path to a language id
by extension and flags lockfiles / minified / vendored paths as generated."""
from __future__ import annotations

import posixpath

_EXT_TO_LANG: dict[str, str] = {
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript", ".cts": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".py": "python", ".pyi": "python",
    ".go": "go", ".rs": "rust", ".java": "java", ".kt": "kotlin", ".kts": "kotlin",
    ".rb": "ruby", ".php": "php",
    ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".cs": "csharp", ".swift": "swift", ".scala": "scala",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".sql": "sql", ".html": "html", ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".md": "markdown", ".markdown": "markdown", ".xml": "xml",
    ".proto": "protobuf", ".graphql": "graphql", ".gql": "graphql",
    ".vue": "vue", ".svelte": "svelte",
}

_BASENAME_TO_LANG: dict[str, str] = {
    "Dockerfile": "dockerfile", "Makefile": "makefile", "Gemfile": "ruby", "Rakefile": "ruby",
}

_GENERATED_BASENAMES: frozenset[str] = frozenset({
    "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb",
    "poetry.lock", "Pipfile.lock", "uv.lock", "go.sum", "Cargo.lock", "composer.lock", "Gemfile.lock",
})

_GENERATED_DIR_SEGMENTS: frozenset[str] = frozenset({
    "node_modules", "vendor", "dist", "build", ".next", "__generated__", "generated",
})


def _basename(path: str) -> str:
    return posixpath.basename(path)


def detect_language(path: str | None) -> str | None:
    """Return a language id for `path`, or None if unknown."""
    if not path:
        return None
    base = _basename(path)
    if base in _BASENAME_TO_LANG:
        return _BASENAME_TO_LANG[base]
    _, ext = posixpath.splitext(base)
    return _EXT_TO_LANG.get(ext.lower())


def is_generated(path: str | None) -> bool:
    """Heuristic: is `path` a lockfile, minified, or vendored/generated output?"""
    if not path:
        return False
    base = _basename(path)
    if base in _GENERATED_BASENAMES:
        return True
    if ".min." in base:
        return True
    segments = [seg for seg in path.split("/") if seg]
    return any(seg in _GENERATED_DIR_SEGMENTS for seg in segments)
