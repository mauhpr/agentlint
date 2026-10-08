"""Stack auto-detection for AgentLint."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from agentlint.packs import PACK_MODULES

logger = logging.getLogger("agentlint")

_SSR_SSG_FRAMEWORKS = {
    "next",
    "nuxt",
    "gatsby",
    "astro",
    "@sveltejs/kit",
    "remix",
    "@angular/ssr",
    "vite-plugin-ssr",
}


def detect_stack(project_dir: str) -> list[str]:
    """Detect the tech stack of a project by scanning for config files.
    Returns a list of pack names to activate, always starting with 'universal'.
    Only returns packs that are actually registered in PACK_MODULES.
    """
    root = Path(project_dir)
    packs = ["universal", "quality"]

    if _has_python(root) and "python" in PACK_MODULES:
        packs.append("python")
    if _has_frontend(root) and "frontend" in PACK_MODULES:
        packs.append("frontend")
    if _has_react(root) and "react" in PACK_MODULES:
        packs.append("react")
    if _has_seo_framework(root) and "seo" in PACK_MODULES:
        packs.append("seo")

    # Additive: use AGENTS.md hints to discover additional packs.
    _add_agents_md_hints(root, packs)

    return packs


def _has_python(root: Path) -> bool:
    return (root / "pyproject.toml").exists() or (root / "setup.py").exists()


def _has_frontend(root: Path) -> bool:
    return (root / "package.json").exists()


def _has_react(root: Path) -> bool:
    package_json = root / "package.json"
    if not package_json.exists():
        return False
    try:
        data = json.loads(package_json.read_text())
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        return "react" in deps
    except (json.JSONDecodeError, OSError):
        return False


def _add_agents_md_hints(root: Path, packs: list[str]) -> None:
    """If AGENTS.md exists, scan for pack-related keywords to enrich detection."""
    from agentlint.agents_md import find_agents_md, map_to_config, parse_agents_md

    agents_path = find_agents_md(str(root))
    if agents_path is None:
        return

    try:
        sections = parse_agents_md(agents_path)
        if not sections:
            return
        mapped = map_to_config(sections)
        for pack in mapped.get("packs", []):
            if pack not in packs and pack in PACK_MODULES:
                packs.append(pack)
    except Exception:
        logger.debug("Failed to parse AGENTS.md for detection hints", exc_info=True)


def _has_seo_framework(root: Path) -> bool:
    package_json = root / "package.json"
    if not package_json.exists():
        return False
    try:
        data = json.loads(package_json.read_text())
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        return bool(_SSR_SSG_FRAMEWORKS & set(deps.keys()))
    except (json.JSONDecodeError, OSError):
        return False


# --- Configuration drift (v2.9.0) -------------------------------------------

_SKIP_DIRS = {
    "node_modules",
    ".git",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "__pycache__",
    ".next",
    ".nuxt",
    "target",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "vendor",
    "site-packages",
    ".cache",
    "coverage",
    ".worktrees",
    "worktrees",
}
_FRONTEND_SUFFIXES = {".tsx", ".jsx", ".vue", ".svelte"}
_MAX_DEPTH = 3
_MAX_ENTRIES = 20_000


def _stack_signals(root: Path) -> dict[str, list[str]]:
    """Shallow, bounded, breadth-first scan for stack evidence below the root.

    Nested repositories and worktrees (directories with their own `.git`) are
    skipped: their files are another checkout's evidence, not this repository's.
    """
    from collections import deque

    signals: dict[str, list[str]] = {"python": [], "frontend": [], "react": [], "seo": []}
    component_files = 0
    seen = 0
    queue: deque[tuple[Path, int]] = deque([(root, 0)])
    while queue and seen < _MAX_ENTRIES:
        directory, depth = queue.popleft()
        try:
            entries = sorted(directory.iterdir(), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            seen += 1
            if entry.is_dir():
                if (
                    depth < _MAX_DEPTH
                    and entry.name not in _SKIP_DIRS
                    and not entry.is_symlink()
                    and not (entry / ".git").exists()
                ):
                    queue.append((entry, depth + 1))
                continue
            rel = entry.relative_to(root).as_posix()
            if entry.name in {"pyproject.toml", "setup.py"}:
                signals["python"].append(rel)
            elif entry.name == "package.json":
                signals["frontend"].append(rel)
                if _has_react(entry.parent):
                    signals["react"].append(rel)
                if _has_seo_framework(entry.parent):
                    signals["seo"].append(rel)
            elif entry.suffix in _FRONTEND_SUFFIXES:
                component_files += 1
    if component_files:
        signals["frontend"].append(f"{component_files} .tsx/.jsx/.vue/.svelte file(s)")
    return signals


def detect_drift(config, project_dir: str) -> list[dict]:
    """Packs the repository shows evidence for but an explicit `packs:` omits.

    Only explicit pack lists can drift (auto-detection follows the repository).
    `projects:` mappings that enable the pack for the evidence's directory, and
    packs listed in `drift_ignore_packs`, are not reported. Never edits config.
    """
    if not getattr(config, "packs_explicit", False):
        return []
    ignored = set(getattr(config, "drift_ignore_packs", []) or [])
    findings = []
    for pack, evidence in _stack_signals(Path(project_dir)).items():
        if not evidence or pack in config.packs or pack in ignored or pack not in PACK_MODULES:
            continue
        uncovered = [
            item
            for item in evidence
            if not any(
                item.startswith(prefix.rstrip("/") + "/") and pack in (proj.get("packs") or [])
                for prefix, proj in (config.projects or {}).items()
            )
        ]
        if uncovered:
            findings.append({"pack": pack, "evidence": uncovered[:5]})
    return findings
