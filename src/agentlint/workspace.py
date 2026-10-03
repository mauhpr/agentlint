"""Explicit, directory-scoped workspace policy composition (no implicit home policy)."""

from __future__ import annotations

import os
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

import yaml

from agentlint.config import CONFIG_FILENAMES, AgentLintConfig
from agentlint.packs import PACK_MODULES, load_rules


def _merge(base: dict, local: dict) -> dict:
    result = deepcopy(base)
    for key, value in local.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_workspace_config(project_dir: str, loader: Callable) -> AgentLintConfig:
    """Merge defaults and nearest repository policy; retain explicitly required rules.

    Repository lists replace default lists, including explicit rule exemptions.
    Packs are additive. Required rules cannot be disabled, severity-degraded, or
    removed by per-file pack mappings. They still honor per-rule path exemptions.
    """
    setting = os.environ.get("AGENTLINT_WORKSPACE_CONFIG")
    if not setting:
        return loader(project_dir)
    path = Path(setting).expanduser().resolve()
    root = path.parent
    project = Path(project_dir).resolve()
    if not project.is_relative_to(root):
        return loader(project_dir)
    if path.name not in CONFIG_FILENAMES or not path.is_file():
        raise ValueError("Workspace config must be an existing AgentLint YAML file")
    # Avoid ambiguity if two recognized filenames coexist.
    chosen = next((root / name for name in CONFIG_FILENAMES if (root / name).is_file()), None)
    if chosen != path:
        raise ValueError("Workspace config is shadowed by another AgentLint filename")
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict) or not isinstance(raw.get("workspace"), dict):
        raise ValueError("Workspace config requires a workspace mapping")
    required = raw["workspace"].get("required_rules", [])
    if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
        raise ValueError("workspace.required_rules must be a list of rule IDs")
    known = {rule.id: rule.pack for rule in load_rules(list(PACK_MODULES))}
    if set(required) - known.keys():
        raise ValueError("workspace.required_rules contains an unknown built-in rule")
    base = loader(str(root), strict=True)
    local_dir = project
    while local_dir != root:
        if any((local_dir / name).is_file() for name in CONFIG_FILENAMES):
            break
        local_dir = local_dir.parent
    local = loader(str(local_dir), strict=True) if local_dir != root else base
    local_raw = {}
    if local_dir != root:
        local_path = next(
            local_dir / name for name in CONFIG_FILENAMES if (local_dir / name).is_file()
        )
        local_raw = yaml.safe_load(local_path.read_text()) or {}
    packs = list(dict.fromkeys([*base.packs, *local.packs, *(known[r] for r in required)]))
    rules = _merge(base.rules, local.rules)
    for rule_id in required:
        if not isinstance(rules.get(rule_id, {}), dict):
            rules[rule_id] = {}
        rules.setdefault(rule_id, {})["enabled"] = True
    custom_dir = local.custom_rules_dir or base.custom_rules_dir
    if custom_dir:
        owner = local_dir if local.custom_rules_dir else root
        custom_dir = str((owner / custom_dir).resolve())
    return AgentLintConfig(
        severity=local.severity if "severity" in local_raw else base.severity,
        packs=packs,
        rules=rules,
        custom_rules_dir=custom_dir,
        circuit_breaker=_merge(base.circuit_breaker, local.circuit_breaker),
        recording=_merge(base.recording, local.recording),
        agentchute=_merge(base.agentchute, local.agentchute),
        projects=_merge(base.projects, local.projects),
        required_rules=list(dict.fromkeys(required)),
        source_paths=list(dict.fromkeys([*base.source_paths, *local.source_paths])),
        exceptions=[*base.exceptions, *local.exceptions] if local_dir != root else base.exceptions,
    )
