"""Rule pack loader."""
from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path

from agentlint.models import Rule

logger = logging.getLogger("agentlint")

PACK_MODULES = {
    "universal": "agentlint.packs.universal",
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
