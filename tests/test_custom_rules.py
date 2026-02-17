"""Tests for custom rules directory loading."""
from __future__ import annotations

from agentlint.packs import load_custom_rules


class TestLoadCustomRules:
    def test_returns_empty_when_dir_missing(self, tmp_path):
        rules = load_custom_rules("nonexistent", str(tmp_path))
        assert rules == []

    def test_loads_rule_from_py_file(self, tmp_path):
        rules_dir = tmp_path / "my_rules"
        rules_dir.mkdir()
        (rules_dir / "my_rule.py").write_text(
            "from agentlint.models import Rule, RuleContext, Violation, HookEvent, Severity\n"
            "\n"
            "class MyRule(Rule):\n"
            "    id = 'my-custom-rule'\n"
            "    description = 'A custom rule'\n"
            "    severity = Severity.WARNING\n"
            "    events = [HookEvent.PRE_TOOL_USE]\n"
            "    pack = 'custom'\n"
            "\n"
            "    def evaluate(self, context: RuleContext) -> list[Violation]:\n"
            "        return []\n"
        )

        rules = load_custom_rules("my_rules", str(tmp_path))
        assert len(rules) == 1
        assert rules[0].id == "my-custom-rule"

    def test_skips_underscored_files(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "__init__.py").write_text("")
        (rules_dir / "_helper.py").write_text("x = 1")

        rules = load_custom_rules("rules", str(tmp_path))
        assert rules == []

    def test_skips_files_without_rule_subclasses(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "utils.py").write_text("def helper(): pass\n")

        rules = load_custom_rules("rules", str(tmp_path))
        assert rules == []

    def test_survives_syntax_error_in_rule_file(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "broken.py").write_text("this is not valid python !!!")

        rules = load_custom_rules("rules", str(tmp_path))
        assert rules == []

    def test_loads_multiple_rules_from_multiple_files(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()

        for i in range(3):
            (rules_dir / f"rule_{i}.py").write_text(
                "from agentlint.models import Rule, RuleContext, Violation, HookEvent, Severity\n"
                "\n"
                f"class Rule{i}(Rule):\n"
                f"    id = 'custom-{i}'\n"
                "    description = 'Custom'\n"
                "    severity = Severity.INFO\n"
                "    events = [HookEvent.PRE_TOOL_USE]\n"
                "    pack = 'custom'\n"
                "\n"
                "    def evaluate(self, context: RuleContext) -> list[Violation]:\n"
                "        return []\n"
            )

        rules = load_custom_rules("rules", str(tmp_path))
        assert len(rules) == 3
        ids = {r.id for r in rules}
        assert ids == {"custom-0", "custom-1", "custom-2"}
