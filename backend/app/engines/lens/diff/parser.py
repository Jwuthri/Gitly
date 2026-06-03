"""Real unified-diff parser -> internal ``ParsedDiff`` (line-level).

Hand-rolled (rather than leaning on ``unidiff``) for exact control over file-status
detection, per-line old/new numbering, stable hunk ids (``h0``, ``h1``, …), and per-file
add/delete counts. Output is close to the lens schema's FileChange/Hunk/DiffLine.
Ported from pr-visual-diff (`app/diff/parser.py`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .language import detect_language, is_generated
from ..models import DiffLineType, FileStatus

# @@ -old_start,old_lines +new_start,new_lines @@ optional section heading
_HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_lines>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_lines>\d+))? @@(?P<header>.*)$"
)


@dataclass
class ParsedLine:
    type: DiffLineType
    content: str
    old_no: int | None
    new_no: int | None


@dataclass
class ParsedHunk:
    id: str
    file: str
    old_file: str | None
    header: str | None
    language: str | None
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[ParsedLine] = field(default_factory=list)


@dataclass
class ParsedFile:
    path: str
    old_path: str | None
    status: FileStatus
    language: str | None
    is_generated: bool
    is_binary: bool
    additions: int
    deletions: int
    hunks: list[ParsedHunk] = field(default_factory=list)

    @property
    def hunk_ids(self) -> list[str]:
        return [h.id for h in self.hunks]


@dataclass
class ParsedDiff:
    files: list[ParsedFile] = field(default_factory=list)

    @property
    def all_hunks(self) -> list[ParsedHunk]:
        return [h for f in self.files for h in f.hunks]


class DiffParseError(ValueError):
    """Raised when input is not a parseable unified diff at all."""


def _strip_prefix(path: str) -> str:
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def _is_dev_null(path: str) -> bool:
    return path == "/dev/null"


class _FileBlock:
    """Mutable accumulator for a single ``diff --git`` block while scanning."""

    def __init__(self) -> None:
        self.header_old_path: str | None = None
        self.header_new_path: str | None = None
        self.git_a_path: str | None = None
        self.git_b_path: str | None = None
        self.rename_from: str | None = None
        self.rename_to: str | None = None
        self.copy_from: str | None = None
        self.copy_to: str | None = None
        self.is_new_file: bool = False
        self.is_deleted_file: bool = False
        self.is_binary: bool = False
        self.hunks: list[ParsedHunk] = []
        self.additions: int = 0
        self.deletions: int = 0


def _resolve_paths(block: _FileBlock) -> tuple[str, str | None]:
    old_raw = block.header_old_path
    new_raw = block.header_new_path

    old_path = None if old_raw is None or _is_dev_null(old_raw) else _strip_prefix(old_raw)
    new_path = None if new_raw is None or _is_dev_null(new_raw) else _strip_prefix(new_raw)

    if old_path is None and not (old_raw and _is_dev_null(old_raw)):
        old_path = block.rename_from or block.copy_from or (
            _strip_prefix(block.git_a_path) if block.git_a_path else None
        )
    if new_path is None and not (new_raw and _is_dev_null(new_raw)):
        new_path = block.rename_to or block.copy_to or (
            _strip_prefix(block.git_b_path) if block.git_b_path else None
        )

    post = new_path or old_path or "unknown"
    pre = old_path
    return post, pre


def _resolve_status(block: _FileBlock, post: str, pre: str | None) -> FileStatus:
    if block.is_new_file or (block.header_old_path and _is_dev_null(block.header_old_path)):
        return FileStatus.added
    if block.is_deleted_file or (block.header_new_path and _is_dev_null(block.header_new_path)):
        return FileStatus.deleted
    if block.copy_from is not None or block.copy_to is not None:
        return FileStatus.copied
    if block.rename_from is not None or block.rename_to is not None:
        return FileStatus.renamed
    if pre is not None and pre != post:
        return FileStatus.renamed
    return FileStatus.modified


def _finalize_block(block: _FileBlock, hunk_counter: list[int]) -> ParsedFile | None:
    if (
        block.header_old_path is None
        and block.header_new_path is None
        and block.git_a_path is None
        and block.git_b_path is None
        and not block.hunks
    ):
        return None

    post, pre = _resolve_paths(block)
    status = _resolve_status(block, post, pre)
    language = detect_language(post)

    for h in block.hunks:
        h.id = f"h{hunk_counter[0]}"
        hunk_counter[0] += 1
        h.file = post
        h.old_file = pre
        h.language = language

    return ParsedFile(
        path=post,
        old_path=pre,
        status=status,
        language=language,
        is_generated=is_generated(post),
        is_binary=block.is_binary,
        additions=block.additions,
        deletions=block.deletions,
        hunks=block.hunks,
    )


def parse_diff(text: str) -> ParsedDiff:
    """Parse a unified diff string into a ``ParsedDiff``. Raises ``DiffParseError`` if the
    input contains no recognizable diff structure at all."""
    if text is None:
        raise DiffParseError("diff is empty")

    lines = text.splitlines()
    files: list[ParsedFile] = []
    hunk_counter = [0]

    block: _FileBlock | None = None
    cur_hunk: ParsedHunk | None = None
    old_no = 0
    new_no = 0
    saw_any_structure = False

    def close_block() -> None:
        nonlocal block, cur_hunk
        if block is not None:
            if cur_hunk is not None:
                block.hunks.append(cur_hunk)
                cur_hunk = None
            parsed = _finalize_block(block, hunk_counter)
            if parsed is not None:
                files.append(parsed)
        block = None

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        if line.startswith("diff --git "):
            saw_any_structure = True
            close_block()
            block = _FileBlock()
            m = re.match(r"^diff --git (a/\S+) (b/\S+)$", line)
            if m:
                block.git_a_path = m.group(1)
                block.git_b_path = m.group(2)
            i += 1
            continue

        if line.startswith("--- ") and block is None:
            saw_any_structure = True
            block = _FileBlock()

        if block is not None and cur_hunk is None:
            if line.startswith("new file mode"):
                block.is_new_file = True
                i += 1
                continue
            if line.startswith("deleted file mode"):
                block.is_deleted_file = True
                i += 1
                continue
            if line.startswith("rename from "):
                block.rename_from = line[len("rename from ") :].strip()
                i += 1
                continue
            if line.startswith("rename to "):
                block.rename_to = line[len("rename to ") :].strip()
                i += 1
                continue
            if line.startswith("copy from "):
                block.copy_from = line[len("copy from ") :].strip()
                i += 1
                continue
            if line.startswith("copy to "):
                block.copy_to = line[len("copy to ") :].strip()
                i += 1
                continue
            if line.startswith("Binary files") or line.startswith("GIT binary patch"):
                block.is_binary = True
                i += 1
                continue
            if line.startswith("--- "):
                block.header_old_path = line[4:].split("\t", 1)[0].strip()
                i += 1
                continue
            if line.startswith("+++ "):
                block.header_new_path = line[4:].split("\t", 1)[0].strip()
                i += 1
                continue
            if (
                line.startswith("index ")
                or line.startswith("old mode ")
                or line.startswith("new mode ")
                or line.startswith("similarity index ")
                or line.startswith("dissimilarity index ")
            ):
                i += 1
                continue

        m = _HUNK_RE.match(line)
        if m is not None:
            saw_any_structure = True
            if block is None:
                block = _FileBlock()
            if cur_hunk is not None:
                block.hunks.append(cur_hunk)
            old_start = int(m.group("old_start"))
            new_start = int(m.group("new_start"))
            old_lines = int(m.group("old_lines")) if m.group("old_lines") is not None else 1
            new_lines = int(m.group("new_lines")) if m.group("new_lines") is not None else 1
            header_text = m.group("header")
            if header_text.startswith(" "):
                header_text = header_text[1:]
            cur_hunk = ParsedHunk(
                id="",
                file="",
                old_file=None,
                header=header_text,
                language=None,
                old_start=old_start,
                old_lines=old_lines,
                new_start=new_start,
                new_lines=new_lines,
                lines=[],
            )
            old_no = old_start
            new_no = new_start
            i += 1
            continue

        if cur_hunk is not None:
            if line.startswith("\\"):
                i += 1
                continue
            marker = line[:1]
            content = line[1:]
            if marker == "+":
                cur_hunk.lines.append(ParsedLine(DiffLineType.add, content, old_no=None, new_no=new_no))
                new_no += 1
                if block is not None:
                    block.additions += 1
            elif marker == "-":
                cur_hunk.lines.append(ParsedLine(DiffLineType.remove, content, old_no=old_no, new_no=None))
                old_no += 1
                if block is not None:
                    block.deletions += 1
            elif marker == " " or line == "":
                cur_hunk.lines.append(ParsedLine(DiffLineType.context, content, old_no=old_no, new_no=new_no))
                old_no += 1
                new_no += 1
            else:
                block.hunks.append(cur_hunk) if block is not None else None
                cur_hunk = None
            i += 1
            continue

        i += 1

    close_block()

    if not saw_any_structure or not files:
        raise DiffParseError("input is not a valid unified diff (no file or hunk headers found)")

    return ParsedDiff(files=files)
