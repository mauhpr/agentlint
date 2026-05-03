"""Kimi Code CLI adapter for AgentLint.

Kimi (Moonshot AI) provides a native hooks system with 13 lifecycle events.
Configuration is done via TOML in ~/.kimi/config.toml using [[hooks]] arrays.

Reference: https://www.kimi-cli.com/en/customization/hooks.html
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agentlint.adapters._utils import (
    is_agentlint_flat_entry,
    resolve_command,
)
from agentlint.adapters.base import AgentAdapter
from agentlint.formats.claude_hooks import ClaudeHookFormatter
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext, to_hook_event


# Mapping from Kimi native event names to generic AgentEvent
_KIMI_EVENT_MAP: dict[str, AgentEvent] = {
    "PreToolUse": AgentEvent.PRE_TOOL_USE,
    "PostToolUse": AgentEvent.POST_TOOL_USE,
    "PostToolUseFailure": AgentEvent.POST_TOOL_FAILURE,
    "UserPromptSubmit": AgentEvent.USER_PROMPT,
    "Stop": AgentEvent.STOP,
    "StopFailure": AgentEvent.STOP,
    "SessionStart": AgentEvent.SESSION_START,
    "SessionEnd": AgentEvent.SESSION_END,
    "SubagentStart": AgentEvent.SUB_AGENT_START,
    "SubagentStop": AgentEvent.SUB_AGENT_STOP,
    "PreCompact": AgentEvent.PRE_COMPACT,
    "PostCompact": AgentEvent.PRE_COMPACT,
    "Notification": AgentEvent.NOTIFICATION,
}

# Mapping from Kimi tool names to NormalizedTool
_KIMI_TOOL_MAP: dict[str, NormalizedTool] = {
    "Shell": NormalizedTool.SHELL,
    "WriteFile": NormalizedTool.FILE_WRITE,
    "StrReplaceFile": NormalizedTool.FILE_EDIT,
    "ReadFile": NormalizedTool.FILE_READ,
    "Grep": NormalizedTool.SEARCH,
    "Glob": NormalizedTool.SEARCH,
    "Task": NormalizedTool.SUB_AGENT,
    "Agent": NormalizedTool.SUB_AGENT,
    "WebFetch": NormalizedTool.WEB_FETCH,
    "WebSearch": NormalizedTool.WEB_SEARCH,
}


def _build_hooks(cmd: str) -> list[dict]:
    """Build the Kimi hooks configuration as TOML-compatible dict entries.

    Kimi uses [[hooks]] arrays in ~/.kimi/config.toml.
    Each hook has: event, command, matcher (optional), timeout (optional).
    """
    return [
        {"event": "PreToolUse", "matcher": "Shell|WriteFile|StrReplaceFile", "_agentlint": "v2", "command": f"{cmd} check --event PreToolUse --adapter kimi", "timeout": 5},
        {"event": "PostToolUse", "matcher": "WriteFile|StrReplaceFile", "_agentlint": "v2", "command": f"{cmd} check --event PostToolUse --adapter kimi", "timeout": 10},
        {"event": "UserPromptSubmit", "_agentlint": "v2", "command": f"{cmd} check --event UserPromptSubmit --adapter kimi", "timeout": 5},
        {"event": "SubagentStart", "_agentlint": "v2", "command": f"{cmd} check --event SubagentStart --adapter kimi", "timeout": 5},
        {"event": "SubagentStop", "_agentlint": "v2", "command": f"{cmd} check --event SubagentStop --adapter kimi", "timeout": 10},
        {"event": "Notification", "_agentlint": "v2", "command": f"{cmd} check --event Notification --adapter kimi", "timeout": 5},
        {"event": "Stop", "_agentlint": "v2", "command": f"{cmd} report --adapter kimi", "timeout": 30},
    ]


def _config_path(scope: str, project_dir: str | None = None) -> Path:
    """Return the path to the Kimi config file."""
    if scope == "user":
        return Path.home() / ".kimi" / "config.toml"
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ".kimi" / "config.toml"


def _read_config(path: Path) -> dict | None:
    """Read and parse TOML config. Returns {} if missing, None if invalid."""
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            import tomllib
            return tomllib.load(f)
    except Exception:
        return None


def _write_config(path: Path, data: dict) -> None:
    """Write TOML config with [[hooks]] arrays. Creates parent dirs if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    # Write non-hooks sections first (preserve existing)
    for key, val in data.items():
        if key == "hooks":
            continue
        if isinstance(val, dict):
            lines.append(f"[{key}]")
            for k, v in val.items():
                lines.append(f'{k} = "{v}"')
            lines.append("")
        elif isinstance(val, str):
            lines.append(f'{key} = "{val}"')
        elif isinstance(val, bool):
            lines.append(f"{key} = {str(val).lower()}")
        elif isinstance(val, int):
            lines.append(f"{key} = {val}")
        elif isinstance(val, float):
            lines.append(f"{key} = {val}")

    # Write hooks arrays
    for hook in data.get("hooks", []):
        lines.append("[[hooks]]")
        for key, val in hook.items():
            if isinstance(val, int):
                lines.append(f"{key} = {val}")
            else:
                lines.append(f'{key} = "{val}"')
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class KimiAdapter(AgentAdapter):
    """AgentAdapter implementation for Kimi Code CLI."""

    @property
    def platform_name(self) -> str:
        return "kimi"

    @property
    def formatter(self) -> ClaudeHookFormatter:
        return ClaudeHookFormatter()

    def resolve_project_dir(self) -> str:
        return (
            os.environ.get("AGENTLINT_PROJECT_DIR")
            or os.environ.get("KIMI_PROJECT_DIR")
            or os.getcwd()
        )

    def resolve_session_key(self) -> str:
        return (
            os.environ.get("AGENTLINT_SESSION_ID")
            or os.environ.get("KIMI_SESSION_ID")
            or f"pid-{os.getppid()}"
        )

    def translate_event(self, native_event: str) -> AgentEvent:
        try:
            return _KIMI_EVENT_MAP[native_event]
        except KeyError:
            raise ValueError(f"Unknown Kimi event: {native_event}")

    def normalize_tool_name(self, native_tool: str) -> str:
        return _KIMI_TOOL_MAP.get(native_tool, NormalizedTool.UNKNOWN).value

    def build_rule_context(
        self,
        event: AgentEvent,
        raw_payload: dict[str, Any],
        project_dir: str,
        session_state: dict,
    ) -> RuleContext:
        tool_input = raw_payload.get("tool_input", {})
        return RuleContext(
            event=to_hook_event(raw_payload.get("event", event)),
            tool_name=raw_payload.get("tool_name", ""),
            tool_input=tool_input,
            project_dir=project_dir,
            config={},
            session_state=session_state,
            prompt=raw_payload.get("prompt"),
            subagent_output=raw_payload.get("last_assistant_message") or raw_payload.get("subagent_output"),
            notification_type=raw_payload.get("notification_type"),
            compact_source=raw_payload.get("compact_source"),
            agent_transcript_path=raw_payload.get("agent_transcript_path"),
            agent_type=raw_payload.get("agent_type"),
            agent_id=raw_payload.get("agent_id"),
            agent_platform="kimi",
        )

    def install_hooks(
        self,
        project_dir: str,
        scope: str = "project",
        dry_run: bool = False,
        cmd: str | None = None,
    ) -> None:
        """Install AgentLint hooks into Kimi config.toml."""
        cmd = cmd or resolve_command()
        path = _config_path(scope, project_dir)
        existing = _read_config(path)

        config = dict(existing or {})
        our_hooks = _build_hooks(cmd)
        hooks = list(config.get("hooks", []))

        # Remove existing agentlint entries
        hooks = [h for h in hooks if not is_agentlint_flat_entry(h)]
        hooks.extend(our_hooks)
        config["hooks"] = hooks

        if dry_run:
            import click
            click.echo(f"\nDry run — would write to {path}:")
            for hook in our_hooks:
                click.echo(f"  [[hooks]]")
                for k, v in hook.items():
                    click.echo(f"    {k} = {v!r}")
            return

        _write_config(path, config)

    def uninstall_hooks(
        self,
        project_dir: str,
        scope: str = "project",
    ) -> None:
        """Remove AgentLint hooks from Kimi config.toml."""
        path = _config_path(scope, project_dir)
        existing = _read_config(path)
        if existing is None:
            return  # Corrupted file — don't touch it
        config = dict(existing)
        hooks = list(config.get("hooks", []))

        hooks = [h for h in hooks if not is_agentlint_flat_entry(h)]

        if hooks:
            config["hooks"] = hooks
        else:
            config.pop("hooks", None)

        if config:
            _write_config(path, config)
        elif path.exists():
            path.unlink(missing_ok=True)
