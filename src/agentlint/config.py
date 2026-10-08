"""Configuration loading and parsing for AgentLint."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from agentlint.detector import detect_stack
from agentlint.models import Severity
from agentlint.packs import PACK_MODULES

logger = logging.getLogger("agentlint")

CONFIG_FILENAMES = ["agentlint.yml", "agentlint.yaml", ".agentlint.yml"]

VALID_SEVERITY_MODES = {"strict", "standard", "relaxed"}

# Rules that are disabled unless explicitly enabled in config.
_DISABLED_BY_DEFAULT = {"git-checkpoint"}


@dataclass
class AgentLintConfig:
    """Parsed AgentLint configuration."""

    severity: str = "standard"
    packs: list[str] = field(default_factory=lambda: ["universal"])
    rules: dict[str, dict] = field(default_factory=dict)
    custom_rules_dir: str | None = None
    circuit_breaker: dict = field(default_factory=dict)
    recording: dict = field(default_factory=dict)
    agentchute: dict = field(default_factory=dict)
    projects: dict[str, dict] = field(default_factory=dict)
    required_rules: list[str] = field(default_factory=list)
    source_paths: list[str] = field(default_factory=list)
    exceptions: list[dict] = field(default_factory=list)
    # Provenance: ordered policy layers ({"kind": "workspace"|"repository", "path"})
    # and, per rule, the layer file that last configured it.
    layers: list[dict] = field(default_factory=list)
    rule_origins: dict[str, str] = field(default_factory=dict)
    # True when `packs:` was written explicitly (stack detection was skipped).
    packs_explicit: bool = False
    # Packs intentionally omitted despite repository evidence (silences drift).
    drift_ignore_packs: list[str] = field(default_factory=list)
    # Evidence receipts: {"receipts_dirs": [...], "max_age": "24h"}.
    evidence: dict = field(default_factory=dict)
    # Core packs (universal, quality) deliberately turned off.
    exclude_packs: list[str] = field(default_factory=list)

    def describe_policy_source(self, rule_id: str, pack: str, *, builtin: bool) -> str:
        """Explain which policy layer makes a rule active, for denial messages."""
        origin = f"built-in {pack} pack" if builtin else f"custom pack '{pack}'"
        workspace = next((x["path"] for x in self.layers if x["kind"] == "workspace"), None)
        if rule_id in self.required_rules and workspace:
            return f"{origin}; required by workspace policy {workspace}"
        if rule_id in self.rule_origins:
            return f"{origin}; configured in {self.rule_origins[rule_id]}"
        if self.layers:
            files = ", ".join(x["path"] for x in self.layers)
            return f"{origin}; default settings (policy files: {files})"
        return f"{origin}; built-in defaults (no policy file)"

    @property
    def is_recording_enabled(self) -> bool:
        return self.recording.get("enabled", False)

    def is_rule_enabled(self, rule_id: str) -> bool:
        if rule_id in self.required_rules:
            return True
        rule_cfg = self.rules.get(rule_id, {})
        if not isinstance(rule_cfg, dict):
            # Treat bare boolean/scalar as enabled shorthand: `no-secrets: false`
            return bool(rule_cfg) if rule_cfg is not None else (rule_id not in _DISABLED_BY_DEFAULT)
        default = rule_id not in _DISABLED_BY_DEFAULT
        return rule_cfg.get("enabled", default)

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

    def resolve_packs_for_file(self, file_path: str, project_dir: str) -> list[str]:
        """Resolve effective packs for a file, checking project overrides."""
        if not self.projects or not file_path:
            return self.packs
        try:
            relative = os.path.relpath(file_path, project_dir)
        except ValueError:
            return self.packs

        best_match = ""
        best_packs = None
        for prefix, project_config in self.projects.items():
            clean = prefix.rstrip("/")
            if (relative.startswith(clean + "/") or relative.startswith(clean + os.sep)) and len(
                clean
            ) > len(best_match):
                best_match = clean
                best_packs = project_config.get("packs")
        return with_core_packs(best_packs, self.exclude_packs) if best_packs else self.packs

    def with_packs(self, packs: list[str]) -> AgentLintConfig:
        """Return a copy with different packs."""
        return replace(self, packs=packs)


# Packs that are always active, whether packs are detected or listed explicitly.
# Remove one only by naming it in `exclude_packs`.
CORE_PACKS = ("universal", "quality")


def with_core_packs(packs: list[str], exclude: list[str] | None = None) -> list[str]:
    """Return packs with the core packs prepended (unless excluded), de-duplicated."""
    excluded = set(exclude or [])
    core = [p for p in CORE_PACKS if p not in excluded]
    return list(dict.fromkeys([*core, *(p for p in packs if p not in excluded)]))


def get_rule_setting(rules_dict: dict, rule_id: str, key: str, default=None):
    """Get config value with cascade: per-rule → global → default.

    Allows users to set global defaults in the ``rules:`` block and
    override them per-rule:

        rules:
          strict_mode: true          # global default
          no-secrets:
            strict_mode: false       # per-rule override
    """
    rule_cfg = rules_dict.get(rule_id, {})
    if isinstance(rule_cfg, dict) and key in rule_cfg:
        return rule_cfg[key]
    if key in rules_dict:
        return rules_dict[key]
    return default


def _load_local_config(project_dir: str, *, strict: bool = False) -> AgentLintConfig:
    """Load config from agentlint.yml or auto-detect defaults."""
    root = Path(project_dir)

    raw = {}
    selected_path: Path | None = None
    for filename in CONFIG_FILENAMES:
        config_path = root / filename
        if config_path.exists():
            selected_path = config_path
            try:
                raw = yaml.safe_load(config_path.read_text()) or {}
            except yaml.YAMLError:
                if strict:
                    raise ValueError(f"Invalid workspace/project YAML: {config_path}") from None
                logger.warning("Invalid YAML in %s, using defaults", config_path)
                raw = {}
            break

    if not isinstance(raw, dict):
        raise ValueError("AgentLint configuration must be a mapping")
    from agentlint.exceptions import validate_exceptions

    exceptions = validate_exceptions(raw.get("exceptions", []))

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
        custom_dir = raw.get("custom_rules_dir")
        for p in packs:
            if p not in PACK_MODULES and not custom_dir:
                logger.warning("Unknown pack '%s' — set custom_rules_dir to use custom packs", p)
    elif stack_mode == "auto":
        packs = detect_stack(project_dir)
    else:
        packs = ["universal"]
    exclude_packs = [x for x in (raw.get("exclude_packs") or []) if isinstance(x, str)]
    packs = with_core_packs(packs, exclude_packs)

    return AgentLintConfig(
        severity=severity,
        packs=packs,
        rules=raw.get("rules", {}),
        custom_rules_dir=raw.get("custom_rules_dir"),
        circuit_breaker=raw.get("circuit_breaker", {}),
        recording=raw.get("recording", {}),
        agentchute=raw.get("agentchute", {}),
        projects=raw.get("projects", {}),
        source_paths=[str(selected_path)] if selected_path else [],
        exceptions=exceptions,
        layers=[{"kind": "repository", "path": str(selected_path)}] if selected_path else [],
        rule_origins=(
            {rule_id: str(selected_path) for rule_id in raw.get("rules", {}) or {}}
            if selected_path and isinstance(raw.get("rules"), dict)
            else {}
        ),
        packs_explicit=bool(explicit_packs),
        drift_ignore_packs=[p for p in (raw.get("drift_ignore_packs") or []) if isinstance(p, str)],
        evidence=raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {},
        exclude_packs=exclude_packs,
    )


def load_config(project_dir: str) -> AgentLintConfig:
    """Load local policy, optionally composed with an explicitly selected workspace."""
    from agentlint.workspace import load_workspace_config

    return load_workspace_config(project_dir, _load_local_config)
