"""Grok CLI adapter for AgentLint.

Grok (xAI) provides a native hooks system with 16 lifecycle events.
Configuration is done via JSON in ~/.grok/user-settings.json.

Reference: https://github.com/superagent-ai/grok-cli
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agentlint.adapters._utils import (
    is_agentlint_nested_entry,
    read_json_config,
    resolve_command,
    write_json_config,
)
from agentlint.adapters.base import AgentAdapter
from agentlint.formats.claude_hooks import ClaudeHookFormatter
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext, to_hook_event


# Mapping from Grok native event names to generic AgentEvent
_GROK_EVENT_MAP: dict[str, AgentEvent] = {
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
    "TaskCreated": AgentEvent.SUB_AGENT_START,
    "TaskCompleted": AgentEvent.TASK_COMPLETED,
    "PreCompact": AgentEvent.PRE_COMPACT,
    "PostCompact": AgentEvent.PRE_COMPACT,
    "Notification": AgentEvent.NOTIFICATION,
    "InstructionsLoaded": AgentEvent.SESSION_START,
    "CwdChanged": AgentEvent.CONFIG_CHANGE,
}

# Mapping from Grok tool names to NormalizedTool
_GROK_TOOL_MAP: dict[str, NormalizedTool] = {
    "bash": NormalizedTool.SHELL,
    "write": NormalizedTool.FILE_WRITE,
    "edit": NormalizedTool.FILE_EDIT,
    "read": NormalizedTool.FILE_READ,
    "grep": NormalizedTool.SEARCH,
    "glob": NormalizedTool.SEARCH,
    "task": NormalizedTool.SUB_AGENT,
    "delegate": NormalizedTool.SUB_AGENT,
    "web_fetch": NormalizedTool.WEB_FETCH,
    "web_search": NormalizedTool.WEB_SEARCH,
    "search_x": NormalizedTool.WEB_SEARCH,
    "search_web": NormalizedTool.WEB_SEARCH,
    "generate_image": NormalizedTool.NOTEBOOK,
    "generate_video": NormalizedTool.NOTEBOOK,
}


def _build_hooks(cmd: str) -> dict:
    """Build the Grok hooks configuration for user-settings.json."""
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "bash|write|edit",
                    "hooks": [
                        {
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event PreToolUse --adapter grok",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "write|edit",
                    "hooks": [
                        {
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event PostToolUse --adapter grok",
                            "timeout": 10,
                        }
                    ],
                }
            ],
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event UserPromptSubmit --adapter grok",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "SubagentStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event SubagentStart --adapter grok",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "SubagentStop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event SubagentStop --adapter grok",
                            "timeout": 10,
                        }
                    ],
                }
            ],
            "Notification": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event Notification --adapter grok",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} report --adapter grok",
                            "timeout": 30,
                        }
                    ],
                }
            ],
        }
    }


def _settings_path(scope: str, project_dir: str | None = None) -> Path:
    """Return the path to the Grok settings file."""
    if scope == "user":
        return Path.home() / ".grok" / "user-settings.json"
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ".grok" / "settings.json"


class GrokAdapter(AgentAdapter):
    """AgentAdapter implementation for Grok CLI."""

    @property
    def platform_name(self) -> str:
        return "grok"

    @property
    def formatter(self) -> ClaudeHookFormatter:
        return ClaudeHookFormatter()

    def resolve_project_dir(self) -> str:
        return (
            os.environ.get("AGENTLINT_PROJECT_DIR")
            or os.environ.get("GROK_PROJECT_DIR")
            or os.getcwd()
        )

    def resolve_session_key(self) -> str:
        return (
            os.environ.get("AGENTLINT_SESSION_ID")
            or os.environ.get("GROK_SESSION_ID")
            or f"pid-{os.getppid()}"
        )

    def translate_event(self, native_event: str) -> AgentEvent:
        try:
            return _GROK_EVENT_MAP[native_event]
        except KeyError:
            raise ValueError(f"Unknown Grok event: {native_event}")

    def normalize_tool_name(self, native_tool: str) -> str:
        return _GROK_TOOL_MAP.get(native_tool, NormalizedTool.UNKNOWN).value

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
            agent_platform="grok",
        )

    def install_hooks(
        self,
        project_dir: str,
        scope: str = "project",
        dry_run: bool = False,
        cmd: str | None = None,
    ) -> None:
        """Install AgentLint hooks into Grok user-settings.json."""
        cmd = cmd or resolve_command()
        path = _settings_path(scope, project_dir)
        existing = read_json_config(path)

        settings = dict(existing or {})
        hooks_template = _build_hooks(cmd)
        hooks = dict(settings.get("hooks", {}))

        for event, our_entries in hooks_template["hooks"].items():
            current = list(hooks.get(event, []))
            current = [e for e in current if not is_agentlint_nested_entry(e)]
            current.extend(our_entries)
            hooks[event] = current

        settings["hooks"] = hooks

        if dry_run:
            import click
            click.echo(f"\nDry run — would write to {path}:")
            click.echo(json.dumps(settings, indent=2))
            return

        write_json_config(path, settings)

    def uninstall_hooks(
        self,
        project_dir: str,
        scope: str = "project",
    ) -> None:
        """Remove AgentLint hooks from Grok settings."""
        path = _settings_path(scope, project_dir)
        existing = read_json_config(path)
        if existing is None:
            return  # Corrupted file — don't touch it
        settings = dict(existing)
        hooks = dict(settings.get("hooks", {}))

        for event in list(hooks):
            filtered = [e for e in hooks[event] if not is_agentlint_nested_entry(e)]
            if filtered:
                hooks[event] = filtered
            else:
                del hooks[event]

        if hooks:
            settings["hooks"] = hooks
        else:
            settings.pop("hooks", None)

        if settings:
            write_json_config(path, settings)
        elif path.exists():
            path.unlink(missing_ok=True)
