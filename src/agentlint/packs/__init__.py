"""Rule pack loader."""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING

from agentlint.models import Rule

if TYPE_CHECKING:
    from agentlint.config import AgentLintConfig

logger = logging.getLogger("agentlint")

PACK_MODULES = {
    "universal": "agentlint.packs.universal",
    "quality": "agentlint.packs.quality",
    "python": "agentlint.packs.python",
    "frontend": "agentlint.packs.frontend",
    "react": "agentlint.packs.react",
    "seo": "agentlint.packs.seo",
    "security": "agentlint.packs.security",
    "autopilot": "agentlint.packs.autopilot",
}


def load_rules(active_packs: list[str]) -> list[Rule]:
    """Load rules from all active packs."""
    rules: list[Rule] = []
    for pack_name in active_packs:
        module_path = PACK_MODULES.get(pack_name)
        if module_path:
            module = importlib.import_module(module_path)
            rules.extend(getattr(module, "RULES", []))
    return rules


def load_project_rules(config: "AgentLintConfig", project_dir: str, *, include_policy: bool = True) -> list[Rule]:
    """Load built-in, installed custom, repo-local custom, and policy rules."""
    rules = load_rules(config.packs)
    rules.extend(r for r in load_installed_rules() if r.pack in config.packs)
    if config.custom_rules_dir:
        rules.extend(r for r in load_custom_rules(config.custom_rules_dir, project_dir) if r.pack in config.packs)
    if include_policy:
        try:
            from agentlint.agentchute.policy import build_policy_rules
            rules.extend(build_policy_rules())
        except Exception:
            logger.debug("Failed to load AgentChute policy rules", exc_info=True)
    return rules


def load_installed_rules() -> list[Rule]:
    """Load custom Rule objects from installed Python entry points."""
    rules: list[Rule] = []
    try:
        eps = entry_points(group="agentlint.rules")
    except TypeError:  # pragma: no cover - older importlib.metadata API
        eps = entry_points().get("agentlint.rules", [])
    for ep in eps:
        try:
            factory = ep.load()
            produced = factory()
            if isinstance(produced, Rule):
                rules.append(produced)
            else:
                for item in produced or []:
                    if isinstance(item, Rule):
                        rules.append(item)
        except Exception:
            logger.exception("Failed to load installed AgentLint rules from %s", ep.name)
    return rules


def load_custom_rules(custom_rules_dir: str, project_dir: str) -> list[Rule]:
    """Load Rule subclasses from .py files in a custom rules directory."""
    root = Path(project_dir) / custom_rules_dir
    if not root.is_dir():
        return []

    rules: list[Rule] = []
    for py_file in sorted(root.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            mod_name = f"agentlint_custom.{py_file.stem}"
            spec = importlib.util.spec_from_file_location(mod_name, py_file)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, Rule)
                    and attr is not Rule
                    and hasattr(attr, "id")
                ):
                    rules.append(attr())
        except Exception:
            logger.exception("Failed to load custom rule from %s", py_file)

    return rules
