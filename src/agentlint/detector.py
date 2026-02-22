"""Stack auto-detection for AgentLint."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from agentlint.packs import PACK_MODULES

logger = logging.getLogger("agentlint")

_SSR_SSG_FRAMEWORKS = {
    "next", "nuxt", "gatsby", "astro", "@sveltejs/kit", "remix",
    "@angular/ssr", "vite-plugin-ssr",
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
