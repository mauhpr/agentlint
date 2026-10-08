"""Translate Codex apply_patch payloads into per-file rule contexts without writes."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from agentlint.models import HookEvent, RuleContext

MAX_PATCH_BYTES = 2_000_000
MAX_FILE_BYTES = 5_000_000
MAX_FILES = 200


_SECRETISH_RE = re.compile(
    r"(?i)\b(?:api[_-]?key|token|secret|passw(?:or)?d|bearer|authorization)\b\S*\s*[:=]?\s*\S+"
    r"|[A-Za-z0-9_\-+/]{24,}"
)
_EXCERPT_CHARS = 120


def _excerpt(text: str) -> str:
    """Return a short single-line excerpt with credential-like values masked."""
    text = _SECRETISH_RE.sub("[redacted]", text.strip())
    if len(text) > _EXCERPT_CHARS:
        text = text[: _EXCERPT_CHARS - 1] + "\u2026"
    return text


class PatchError(ValueError):
    """A patch could not be fully inspected; do not silently allow a partial check.

    Location details are optional so envelope-level failures stay simple, while
    hunk failures can name the file, hunk, repeated context and candidate lines.
    """

    def __init__(
        self,
        message: str,
        *,
        path: str | None = None,
        hunk: int | None = None,
        reason: str | None = None,
        excerpt: str | None = None,
        candidate_lines: list[int] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.path = path
        self.hunk = hunk
        self.reason = reason
        self.excerpt = excerpt
        self.candidate_lines = candidate_lines or []

    @property
    def line(self) -> int | None:
        return self.candidate_lines[0] if self.candidate_lines else None

    def describe(self) -> str:
        """Human-readable message including every known location detail."""
        if self.path is None:
            return self.message
        where = f"{self.path}" + (f" hunk {self.hunk}" if self.hunk else "")
        text = f"{where}: {self.message}"
        if self.excerpt:
            text += f" (context starts with: `{self.excerpt}`)"
        if len(self.candidate_lines) > 1:
            shown = ", ".join(str(n) for n in self.candidate_lines[:10])
            more = "" if len(self.candidate_lines) <= 10 else ", \u2026"
            text += f"; matches at lines {shown}{more}"
        return text

    def correction(self) -> str:
        if self.reason == "ambiguous":
            return (
                "Add more unique surrounding context lines to this hunk so it matches "
                "exactly once. An `@@` anchor only skips matches before the anchor line."
            )
        if self.reason in {"missing", "anchor-missing"}:
            return (
                "Re-read the file; the hunk context (or anchor) must match the current "
                "content exactly, in order after any previous hunk."
            )
        return "Use a supported, unambiguous patch; no files were changed by AgentLint."


def _path(value: str, root: Path, directory: Path) -> Path:
    path = (directory / value).resolve()
    if not value or not path.is_relative_to(root) or path == root:
        raise PatchError("Patch path is outside the selected project")
    return path


def _read(path: Path) -> str:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise PatchError("File exceeds the patch inspection size limit")
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PatchError("Could not read a patch input file") from exc


def _update(before: str, body: list[str], path: str | None = None) -> str:
    """Apply exact or trailing-whitespace-normalized, unambiguous hunks in memory."""
    source = before.splitlines()
    cursor = 0
    output: list[str] = []
    i = 0
    hunk = 0
    while i < len(body):
        hunk += 1
        anchor = None
        if body[i].startswith("@@"):
            anchor = body[i][2:].strip()
            i += 1
        old: list[str] = []
        new: list[str] = []
        eof = False
        while i < len(body) and not body[i].startswith("@@"):
            line = body[i]
            i += 1
            if line == "*** End of File":
                eof = True
                if i != len(body):
                    raise PatchError(
                        "Unexpected data after End of File", path=path, hunk=hunk, reason="syntax"
                    )
                break
            if not line or line[0] not in " +-":
                raise PatchError(
                    "Invalid patch hunk line (expected ' ', '+' or '-' prefix)",
                    path=path,
                    hunk=hunk,
                    reason="syntax",
                    excerpt=_excerpt(line) or None,
                )
            if line[0] in " -":
                old.append(line[1:])
            if line[0] in " +":
                new.append(line[1:])
        start = cursor
        if anchor:
            matches = [n for n in range(cursor, len(source)) if source[n].strip() == anchor]
            if not matches:
                raise PatchError(
                    "Patch anchor does not match the input file",
                    path=path,
                    hunk=hunk,
                    reason="anchor-missing",
                    excerpt=_excerpt(anchor),
                )
            start = matches[0] + 1
        if not old:
            position = len(source)
        else:
            positions = [
                n
                for n in range(start, len(source) - len(old) + 1)
                if source[n : n + len(old)] == old and (not eof or n + len(old) == len(source))
            ]
            if not positions:
                positions = [
                    n
                    for n in range(start, len(source) - len(old) + 1)
                    if [s.rstrip() for s in source[n : n + len(old)]] == [s.rstrip() for s in old]
                    and (not eof or n + len(old) == len(source))
                ]
            if len(positions) != 1:
                first = next((line for line in old if line.strip()), old[0])
                if positions:
                    raise PatchError(
                        f"Patch hunk is ambiguous: its {len(old)}-line context matches "
                        f"{len(positions)} places in the input file",
                        path=path,
                        hunk=hunk,
                        reason="ambiguous",
                        excerpt=_excerpt(first),
                        candidate_lines=[n + 1 for n in positions],
                    )
                raise PatchError(
                    "Patch hunk context was not found in the input file",
                    path=path,
                    hunk=hunk,
                    reason="missing",
                    excerpt=_excerpt(first),
                )
            position = positions[0]
        output.extend(source[cursor:position])
        output.extend(new)
        cursor = position + len(old)
    output.extend(source[cursor:])
    return "\n".join(output) + ("\n" if output else "")


def patch_contexts(context: RuleContext) -> list[RuleContext]:
    """Inspect all add/update/delete/rename targets, including both sides of a move."""
    patch = context.tool_input.get("command")
    if not isinstance(patch, str) or len(patch.encode()) > MAX_PATCH_BYTES:
        raise PatchError("Missing or oversized patch")
    lines = patch.strip().splitlines()
    if len(lines) < 3 or lines[0] != "*** Begin Patch" or lines[-1] != "*** End Patch":
        raise PatchError("Expected a complete apply_patch envelope")
    root = Path(context.project_dir).resolve()
    directory = Path(context.working_directory or root).resolve()
    if not directory.is_relative_to(root):
        raise PatchError("Patch working directory is outside the selected project")
    pre = context.event == HookEvent.PRE_TOOL_USE
    cache = context.session_state.setdefault("file_cache", {})
    contexts: list[RuleContext] = []
    seen: set[Path] = set()
    i = 1

    def emit(path: Path, before: str | None, after: str, action: str) -> None:
        if path in seen:
            raise PatchError("Repeated patch target")
        seen.add(path)
        if len(seen) > MAX_FILES:
            raise PatchError("Patch exceeds the file inspection limit")
        if pre and before is not None:
            cache[str(path)] = before
        if not pre:
            before = cache.pop(str(path), None)
        payload = {
            "file_path": str(path),
            "content": after,
            "old_string": before or "",
            "new_string": after,
            "patch_action": action,
        }
        contexts.append(
            replace(
                context,
                tool_name="Write" if action == "add" else "Edit",
                tool_input=payload,
                file_content=after,
                file_content_before=before,
            )
        )

    while i < len(lines) - 1:
        header = lines[i]
        i += 1
        action = next(
            (
                name
                for name in ("Add", "Update", "Delete")
                if header.startswith(f"*** {name} File: ")
            ),
            None,
        )
        if action is None:
            raise PatchError("Unknown patch operation")
        path = _path(header.split(": ", 1)[1], root, directory)
        destination = path
        if action == "Update" and i < len(lines) - 1 and lines[i].startswith("*** Move to: "):
            destination = _path(lines[i].split(": ", 1)[1], root, directory)
            i += 1
        body: list[str] = []
        while i < len(lines) - 1 and not any(
            lines[i].startswith(f"*** {name} File: ") for name in ("Add", "Update", "Delete")
        ):
            body.append(lines[i])
            i += 1
        if action == "Delete" and body:
            raise PatchError("Delete operation cannot contain a hunk")
        if action == "Add" and any(not line.startswith("+") for line in body):
            raise PatchError("Invalid Add File content")
        if pre:
            if action == "Add":
                if path.exists():
                    raise PatchError("Add File would overwrite an existing file")
                before = None
                after = "\n".join(line[1:] for line in body) + ("\n" if body else "")
            else:
                before = _read(path)
                display = path.relative_to(root).as_posix()
                after = "" if action == "Delete" else _update(before, body, display)
            if destination != path and destination.exists():
                raise PatchError("Move would overwrite an existing file")
        else:
            before = None
            after = "" if action == "Delete" else _read(destination)
        if destination != path:
            emit(path, before, "", "delete")
            emit(destination, None, after, "add")
        else:
            emit(path, before, after, action.lower())
    return contexts
