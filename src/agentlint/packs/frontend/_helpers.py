"""Shared helpers for frontend pack rules."""

from __future__ import annotations

_FRONTEND_EXTENSIONS = {".tsx", ".jsx", ".vue", ".svelte", ".html"}
_WRITE_TOOLS = {"Write", "Edit"}


def is_frontend_file(file_path: str | None) -> bool:
    """Return True if file_path has a frontend extension."""
    if not file_path:
        return False
    return any(file_path.endswith(ext) for ext in _FRONTEND_EXTENSIONS)
