"""Configuration loading and parsing for AgentLint."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from agentlint.detector import detect_stack
from agentlint.models import Severity
from agentlint.packs import PACK_MODULES

logger = logging.getLogger("agentlint")

CONFIG_FILENAMES = ["agentlint.yml", "agentlint.yaml", ".agentlint.yml"]

VALID_SEVERITY_MODES = {"strict", "standard", "relaxed"}


@dataclass
class AgentLintConfig:
    """Parsed AgentLint configuration."""
    severity: str = "standard"
    packs: list[str] = field(default_factory=lambda: ["universal"])
    rules: dict[str, dict] = field(default_factory=dict)
    custom_rules_dir: str | None = None

    def is_rule_enabled(self, rule_id: str) -> bool:
        rule_cfg = self.rules.get(rule_id, {})
        return rule_cfg.get("enabled", True)

    def get_rule_config(self, rule_id: str) -> dict:
        return self.rules.get(rule_id, {})

    def effective_severity(self, base: Severity) -> Severity:
        if self.severity == "strict":
            if base == Severity.WARNING:
                return Severity.ERROR
            if base == Severity.INFO:
                return Severity.WARNING
        elif self.severity == "relaxed":
            if base == Severity.WARNING:
                return Severity.INFO
        return base


def load_config(project_dir: str) -> AgentLintConfig:
    """Load config from agentlint.yml or auto-detect defaults."""
    root = Path(project_dir)

    raw = {}
    for filename in CONFIG_FILENAMES:
        config_path = root / filename
        if config_path.exists():
            raw = yaml.safe_load(config_path.read_text()) or {}
            break

    # Validate severity
    severity = raw.get("severity", "standard")
    if severity not in VALID_SEVERITY_MODES:
        logger.warning("Invalid severity '%s', falling back to 'standard'", severity)
        severity = "standard"

    # Determine packs
    stack_mode = raw.get("stack", "auto")
    explicit_packs = raw.get("packs")

    if explicit_packs:
        packs = explicit_packs
        # Warn about unregistered packs
        for p in packs:
            if p not in PACK_MODULES:
                logger.warning("Unknown pack '%s' in config (not registered)", p)
    elif stack_mode == "auto":
        packs = detect_stack(project_dir)
    else:
        packs = ["universal"]

    return AgentLintConfig(
        severity=severity,
        packs=packs,
        rules=raw.get("rules", {}),
        custom_rules_dir=raw.get("custom_rules_dir"),
    )
