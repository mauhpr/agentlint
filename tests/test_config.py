"""Tests for configuration loading and parsing."""
from __future__ import annotations

import json

import yaml

from agentlint.config import AgentLintConfig, load_config
from agentlint.models import Severity


class TestLoadConfig:
    def test_default_config_when_no_file(self, tmp_path):
        config = load_config(str(tmp_path))
        assert config.severity == "standard"
        assert "universal" in config.packs
        assert config.rules == {}
        assert config.custom_rules_dir is None

    def test_loads_from_agentlint_yml(self, tmp_path):
        cfg = {"severity": "strict", "rules": {"R001": {"enabled": False}}}
        (tmp_path / "agentlint.yml").write_text(yaml.dump(cfg))
        config = load_config(str(tmp_path))
        assert config.severity == "strict"
        assert config.rules == {"R001": {"enabled": False}}

    def test_loads_from_agentlint_yaml(self, tmp_path):
        cfg = {"severity": "relaxed"}
        (tmp_path / "agentlint.yaml").write_text(yaml.dump(cfg))
        config = load_config(str(tmp_path))
        assert config.severity == "relaxed"

    def test_loads_from_dot_agentlint_yml(self, tmp_path):
        cfg = {"severity": "strict"}
        (tmp_path / ".agentlint.yml").write_text(yaml.dump(cfg))
        config = load_config(str(tmp_path))
        assert config.severity == "strict"

    def test_first_config_file_wins(self, tmp_path):
        (tmp_path / "agentlint.yml").write_text(yaml.dump({"severity": "strict"}))
        (tmp_path / "agentlint.yaml").write_text(yaml.dump({"severity": "relaxed"}))
        config = load_config(str(tmp_path))
        assert config.severity == "strict"

    def test_auto_detect_when_stack_is_auto(self, tmp_path):
        """Auto-detect only returns packs that are registered in PACK_MODULES."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        config = load_config(str(tmp_path))
        # "python" pack is not yet registered, so it's not included
        assert "universal" in config.packs

    def test_auto_detect_default_when_no_stack_key(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        (tmp_path / "agentlint.yml").write_text(yaml.dump({"severity": "standard"}))
        config = load_config(str(tmp_path))
        assert "universal" in config.packs

    def test_explicit_packs_override_auto_detect(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        cfg = {"packs": ["universal", "custom-pack"]}
        (tmp_path / "agentlint.yml").write_text(yaml.dump(cfg))
        config = load_config(str(tmp_path))
        assert config.packs == ["universal", "custom-pack"]
        assert "python" not in config.packs

    def test_custom_rules_dir(self, tmp_path):
        cfg = {"custom_rules_dir": "my_rules/"}
        (tmp_path / "agentlint.yml").write_text(yaml.dump(cfg))
        config = load_config(str(tmp_path))
        assert config.custom_rules_dir == "my_rules/"

    def test_empty_config_file(self, tmp_path):
        (tmp_path / "agentlint.yml").write_text("")
        config = load_config(str(tmp_path))
        assert config.severity == "standard"
        assert "universal" in config.packs

    def test_invalid_severity_falls_back_to_standard(self, tmp_path):
        cfg = {"severity": "banana"}
        (tmp_path / "agentlint.yml").write_text(yaml.dump(cfg))
        config = load_config(str(tmp_path))
        assert config.severity == "standard"

    def test_yaml_syntax_error_treated_as_empty(self, tmp_path):
        """Invalid YAML should gracefully fall back to defaults."""
        (tmp_path / "agentlint.yml").write_text(": invalid\n  yaml: [")
        config = load_config(str(tmp_path))
        assert config.severity == "standard"
        assert "universal" in config.packs

    def test_whitespace_only_config_file(self, tmp_path):
        """Config file with only whitespace should use defaults."""
        (tmp_path / "agentlint.yml").write_text("   \n\n  \n")
        config = load_config(str(tmp_path))
        assert config.severity == "standard"
        assert "universal" in config.packs

    def test_unknown_pack_name_still_loads(self, tmp_path):
        """Unknown pack names in explicit config should load but log a warning."""
        cfg = {"packs": ["universal", "nonexistent-pack"]}
        (tmp_path / "agentlint.yml").write_text(yaml.dump(cfg))
        config = load_config(str(tmp_path))
        # Config still loads — the warning is logged
        assert config.packs == ["universal", "nonexistent-pack"]


class TestAgentLintConfig:
    def test_is_rule_enabled_default_true(self):
        config = AgentLintConfig()
        assert config.is_rule_enabled("R001") is True

    def test_is_rule_enabled_when_disabled(self):
        config = AgentLintConfig(rules={"R001": {"enabled": False}})
        assert config.is_rule_enabled("R001") is False

    def test_is_rule_enabled_when_explicitly_enabled(self):
        config = AgentLintConfig(rules={"R001": {"enabled": True}})
        assert config.is_rule_enabled("R001") is True

    def test_get_rule_config_returns_config(self):
        rule_cfg = {"enabled": True, "max_lines": 500}
        config = AgentLintConfig(rules={"R001": rule_cfg})
        assert config.get_rule_config("R001") == rule_cfg

    def test_get_rule_config_returns_empty_dict_for_unknown(self):
        config = AgentLintConfig()
        assert config.get_rule_config("UNKNOWN") == {}

    def test_effective_severity_standard_mode(self):
        config = AgentLintConfig(severity="standard")
        assert config.effective_severity(Severity.ERROR) == Severity.ERROR
        assert config.effective_severity(Severity.WARNING) == Severity.WARNING
        assert config.effective_severity(Severity.INFO) == Severity.INFO

    def test_effective_severity_strict_mode(self):
        config = AgentLintConfig(severity="strict")
        assert config.effective_severity(Severity.ERROR) == Severity.ERROR
        assert config.effective_severity(Severity.WARNING) == Severity.ERROR
        assert config.effective_severity(Severity.INFO) == Severity.WARNING

    def test_effective_severity_relaxed_mode(self):
        config = AgentLintConfig(severity="relaxed")
        assert config.effective_severity(Severity.ERROR) == Severity.ERROR
        assert config.effective_severity(Severity.WARNING) == Severity.INFO
        assert config.effective_severity(Severity.INFO) == Severity.INFO
