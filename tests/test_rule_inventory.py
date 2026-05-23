"""Release-facing rule inventory checks."""
from __future__ import annotations

from agentlint.packs import PACK_MODULES, load_rules


def test_builtin_rule_inventory_matches_release_docs() -> None:
    counts = {pack: len(load_rules([pack])) for pack in PACK_MODULES}
    assert counts == {
        "universal": 24,
        "quality": 7,
        "python": 6,
        "frontend": 8,
        "react": 3,
        "seo": 4,
        "security": 7,
        "autopilot": 18,
    }
    assert sum(counts.values()) == 77
