"""Shared helpers for SEO pack rules."""
from __future__ import annotations

_SEO_EXTENSIONS = {".tsx", ".jsx", ".vue", ".svelte", ".html"}
_WRITE_TOOLS = {"Write", "Edit"}

_DEFAULT_PAGE_PATTERNS = {"pages/", "app/", "routes/"}


def is_page_file(file_path: str | None, page_patterns: set[str] | None = None) -> bool:
    """Return True if file_path looks like a page/route file with a frontend extension."""
    if not file_path:
        return False
    if not any(file_path.endswith(ext) for ext in _SEO_EXTENSIONS):
        return False
    patterns = page_patterns or _DEFAULT_PAGE_PATTERNS
    return any(p in file_path for p in patterns)
