"""Path classification utilities shared across rules.

Some rules ought to treat paths under ephemeral/scratch directories as safe
(e.g. ``rm -rf /tmp/foo`` is not the destruction of important data, and
``echo > /tmp/scratch.txt`` is not bypassing Edit/Write tooling for source
files). This module centralises the convention so individual rules don't
re-implement it.
"""
from __future__ import annotations

import os

# Default ephemeral/scratch path prefixes recognised as "safe" across rules.
# - ``/tmp/`` and ``/private/tmp/`` are POSIX scratch.
# - ``/var/folders/`` is the macOS per-user TMPDIR root.
SAFE_PATH_PREFIXES: tuple[str, ...] = (
    "/tmp/",
    "/private/tmp/",
    "/var/folders/",
)


def _expand_tmpdir_prefix(prefix: str) -> str | None:
    """Resolve ``$TMPDIR`` references in a prefix; return None if undefined."""
    if "$TMPDIR" not in prefix:
        return prefix
    tmpdir = os.environ.get("TMPDIR")
    if not tmpdir:
        return None
    expanded = prefix.replace("$TMPDIR", tmpdir.rstrip("/"))
    return expanded if expanded.endswith("/") else expanded + "/"


def is_safe_path(path: str, extra_prefixes: list[str] | None = None) -> bool:
    """Return True when ``path`` lives under a known-safe (ephemeral) prefix.

    Recognised by default: ``/tmp/``, ``/private/tmp/``, ``/var/folders/``.
    Callers may pass ``extra_prefixes`` to extend the list (e.g. from
    per-rule config). Prefixes containing literal ``$TMPDIR`` are resolved
    against the environment at call time.

    Path matching is prefix-only — relative paths like ``./scratch`` or
    bare names like ``foo`` never match. Empty input returns False.
    """
    if not path:
        return False
    candidates: list[str] = list(SAFE_PATH_PREFIXES)
    if extra_prefixes:
        candidates.extend(extra_prefixes)
    for prefix in candidates:
        resolved = _expand_tmpdir_prefix(prefix)
        if resolved is None:
            continue
        if path.startswith(resolved):
            return True
    return False
