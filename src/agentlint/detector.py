"""Stack auto-detection for AgentLint."""
from __future__ import annotations

import json
from pathlib import Path

from agentlint.packs import PACK_MODULES

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
    packs = ["universal"]

    if _has_python(root) and "python" in PACK_MODULES:
        packs.append("python")
    if _has_frontend(root) and "frontend" in PACK_MODULES:
        packs.append("frontend")
    if _has_react(root) and "react" in PACK_MODULES:
        packs.append("react")
    if _has_seo_framework(root) and "seo" in PACK_MODULES:
        packs.append("seo")

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
