"""Translate Codex apply_patch payloads into per-file rule contexts without writes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from agentlint.models import HookEvent, RuleContext

MAX_PATCH_BYTES = 2_000_000
MAX_FILE_BYTES = 5_000_000
MAX_FILES = 200


class PatchError(ValueError):
    """A patch could not be fully inspected; do not silently allow a partial check."""


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


def _update(before: str, body: list[str]) -> str:
    """Apply exact or trailing-whitespace-normalized, unambiguous hunks in memory."""
    source = before.splitlines()
    cursor = 0
    output: list[str] = []
    i = 0
    while i < len(body):
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
                    raise PatchError("Unexpected data after End of File")
                break
            if not line or line[0] not in " +-":
                raise PatchError("Invalid patch hunk")
            if line[0] in " -":
                old.append(line[1:])
            if line[0] in " +":
                new.append(line[1:])
        start = cursor
        if anchor:
            matches = [n for n in range(cursor, len(source)) if source[n].strip() == anchor]
            if not matches:
                raise PatchError("Patch anchor does not match the input file")
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
                raise PatchError("Patch hunk is missing or ambiguous in the input file")
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
                after = "" if action == "Delete" else _update(before, body)
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
