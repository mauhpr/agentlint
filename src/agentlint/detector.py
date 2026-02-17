"""Stack auto-detection for AgentLint."""
from __future__ import annotations

import json
from pathlib import Path

from agentlint.packs import PACK_MODULES


def detect_stack(project_dir: str) -> list[str]:
    """Detect the tech stack of a project by scanning for config files.
    Returns a list of pack names to activate, always starting with 'universal'.
    Only returns packs that are actually registered in PACK_MODULES.
    """
    root = Path(project_dir)
    packs = ["universal"]

    if _has_python(root) and "python" in PACK_MODULES:
        packs.append("python")
    if _has_react(root) and "react" in PACK_MODULES:
        packs.append("react")

    return packs


def _has_python(root: Path) -> bool:
    return (root / "pyproject.toml").exists() or (root / "setup.py").exists()


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
