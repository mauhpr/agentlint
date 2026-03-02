"""Test that the autopilot pack scaffolding loads correctly."""
from agentlint.packs import PACK_MODULES, load_rules


def test_autopilot_registered_in_pack_modules():
    assert "autopilot" in PACK_MODULES


def test_autopilot_loads_without_error():
    rules = load_rules(["autopilot"])
    assert isinstance(rules, list)
    # 6 original + 6 new safety rules = 12
    assert len(rules) == 12
