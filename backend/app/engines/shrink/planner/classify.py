"""Classify a file change into a semantic category, and detect generated files.

Categories drive slice ordering: dependencies/config first, then migrations, then source,
then tests, then docs. Tests are pulled next to the source they exercise by the planner.
"""
from __future__ import annotations

import re
from enum import IntEnum

from ..diff.models import FileChange


class Category(IntEnum):
    """Value is the ordering rank — lower sorts earlier in the stack."""

    DEPS = 0
    CONFIG = 1
    MIGRATION = 2
    SOURCE = 3
    TEST = 4
    DOCS = 5


_DEPS_NAMES = {
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "requirements.txt", "requirements-dev.txt", "pyproject.toml", "poetry.lock",
    "Pipfile", "Pipfile.lock", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock",
    "Gemfile", "Gemfile.lock", "pom.xml", "build.gradle", "build.gradle.kts",
}
_CONFIG_RE = re.compile(
    r"(^|/)(\.env|Dockerfile|docker-compose|tsconfig\.json|\.eslintrc|\.prettierrc|"
    r".*\.config\.(js|ts|mjs|cjs)|.*\.ya?ml|.*\.toml|.*\.ini)($|.*)"
)
_MIGRATION_RE = re.compile(r"(^|/)(migrations?|alembic)(/|$)|\.sql$")
_TEST_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec)(/|$)|(^|/)test_[^/]*$|_test\.[a-z]+$|"
    r"\.(test|spec)\.[a-z]+$"
)
_DOCS_RE = re.compile(r"\.(md|rst|mdx)$|(^|/)docs?(/|$)|(^|/)README")
_GENERATED_RE = re.compile(
    r"\.pb\.go$|_pb2\.py$|\.generated\.|(^|/)(dist|build|__generated__)(/|$)|"
    r"\.min\.(js|css)$|\.snap$|\.lock$"
)


def is_generated(path: str) -> bool:
    return bool(_GENERATED_RE.search(path)) or path.split("/")[-1] in {
        "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
        "Cargo.lock", "Gemfile.lock", "go.sum",
    }


def classify(file: FileChange) -> Category:
    path = file.path
    name = path.split("/")[-1]
    if name in _DEPS_NAMES:
        return Category.DEPS
    if _MIGRATION_RE.search(path):
        return Category.MIGRATION
    if _TEST_RE.search(path):
        return Category.TEST
    if _DOCS_RE.search(path):
        return Category.DOCS
    if _CONFIG_RE.search(path):
        return Category.CONFIG
    return Category.SOURCE


def module_of(path: str, depth: int = 2) -> str:
    """A coarse grouping key: the file's directory, capped at `depth` segments."""
    parts = path.split("/")
    if len(parts) <= 1:
        return "(root)"
    return "/".join(parts[:-1][:depth])
