"""Rule pack loader."""
from __future__ import annotations

from agentlint.models import Rule

PACK_MODULES = {
    "universal": "agentlint.packs.universal",
}


def load_rules(active_packs: list[str]) -> list[Rule]:
    """Load rules from all active packs."""
    import importlib

    rules: list[Rule] = []
    for pack_name in active_packs:
        module_path = PACK_MODULES.get(pack_name)
        if module_path:
            module = importlib.import_module(module_path)
            rules.extend(getattr(module, "RULES", []))
    return rules
