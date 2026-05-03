"""Hook installation and removal for Claude Code settings.json.

This module re-exports Claude-specific setup utilities for backward
compatibility. New code should use agentlint.adapters.claude.ClaudeAdapter.
"""
from __future__ import annotations

from agentlint.adapters._utils import (
    is_agentlint_nested_entry as _is_agentlint_entry,
    read_json_config as read_settings,
    resolve_command as _resolve_command,
    write_json_config as write_settings,
)
from agentlint.adapters.claude import (
    _build_hooks as build_hooks,
    _settings_path as settings_path,
    ClaudeAdapter,
)

# Backward-compatible alias
AGENTLINT_HOOKS: dict = build_hooks("agentlint")


def merge_hooks(existing: dict, agentlint_cmd: str | None = None) -> dict:
    """Merge agentlint hooks into existing settings (idempotent)."""
    cmd = agentlint_cmd or _resolve_command()
    hooks_template = build_hooks(cmd)

    settings = dict(existing)
    hooks = dict(settings.get("hooks", {}))

    for event, our_entries in hooks_template.items():
        current = list(hooks.get(event, []))
        current = [e for e in current if not _is_agentlint_entry(e)]
        current.extend(our_entries)
        hooks[event] = current

    settings["hooks"] = hooks
    return settings


def remove_hooks(existing: dict) -> dict:
    """Remove all agentlint hooks from settings."""
    settings = dict(existing)
    hooks = dict(settings.get("hooks", {}))

    for event in list(hooks):
        filtered = [e for e in hooks[event] if not _is_agentlint_entry(e)]
        if filtered:
            hooks[event] = filtered
        else:
            del hooks[event]

    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)

    return settings
