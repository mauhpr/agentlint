"""Claude Code adapter for AgentLint."""
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
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext


# Mapping from Claude Code native event names to generic AgentEvent
_CLAUDE_EVENT_MAP: dict[str, AgentEvent] = {
    "PreToolUse": AgentEvent.PRE_TOOL_USE,
    "PostToolUse": AgentEvent.POST_TOOL_USE,
    "PostToolUseFailure": AgentEvent.POST_TOOL_FAILURE,
    "UserPromptSubmit": AgentEvent.USER_PROMPT,
    "SessionStart": AgentEvent.SESSION_START,
    "SessionEnd": AgentEvent.SESSION_END,
    "SubagentStart": AgentEvent.SUB_AGENT_START,
    "SubagentStop": AgentEvent.SUB_AGENT_STOP,
    "Notification": AgentEvent.NOTIFICATION,
    "PreCompact": AgentEvent.PRE_COMPACT,
    "PermissionRequest": AgentEvent.PERMISSION_REQUEST,
    "ConfigChange": AgentEvent.CONFIG_CHANGE,
    "WorktreeCreate": AgentEvent.WORKTREE_CREATE,
    "WorktreeRemove": AgentEvent.WORKTREE_REMOVE,
    "TeammateIdle": AgentEvent.TEAMMATE_IDLE,
    "TaskCompleted": AgentEvent.TASK_COMPLETED,
    "Stop": AgentEvent.STOP,
}

# Mapping from Claude tool names to NormalizedTool
_CLAUDE_TOOL_MAP: dict[str, NormalizedTool] = {
    "Write": NormalizedTool.FILE_WRITE,
    "Edit": NormalizedTool.FILE_EDIT,
    "Bash": NormalizedTool.SHELL,
    "Read": NormalizedTool.FILE_READ,
    "Glob": NormalizedTool.SEARCH,
    "Grep": NormalizedTool.SEARCH,
    "Agent": NormalizedTool.SUB_AGENT,
    "Task": NormalizedTool.SUB_AGENT,
    "WebFetch": NormalizedTool.WEB_FETCH,
    "WebSearch": NormalizedTool.WEB_SEARCH,
    "NotebookEdit": NormalizedTool.NOTEBOOK,
    "MultiEdit": NormalizedTool.FILE_EDIT,
}


def _build_hooks(cmd: str) -> dict:
    """Build the agentlint hooks dict for Claude Code settings.json."""
    return {
        "PreToolUse": [
            {
                "matcher": "Bash|Edit|Write",
                "hooks": [
                    {
                        "type": "command",
                        "_agentlint": "v2",
                        "command": f"{cmd} check --event PreToolUse",
                        "timeout": 5,
                    }
                ],
            }
        ],
        "PostToolUse": [
            {
                "matcher": "Edit|Write",
                "hooks": [
                    {
                        "type": "command",
                        "_agentlint": "v2",
                        "command": f"{cmd} check --event PostToolUse",
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
                        "command": f"{cmd} check --event UserPromptSubmit",
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
                        "command": f"{cmd} check --event SubagentStart",
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
                        "command": f"{cmd} check --event SubagentStop",
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
                        "command": f"{cmd} check --event Notification",
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
                        "command": f"{cmd} report",
                        "timeout": 30,
                    }
                ],
            }
        ],
    }


def _settings_path(scope: str, project_dir: str | None = None) -> Path:
    """Return the path to the Claude Code settings file."""
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ".claude" / "settings.json"


class ClaudeAdapter(AgentAdapter):
    """AgentAdapter implementation for Claude Code."""

    @property
    def platform_name(self) -> str:
        return "claude"

    @property
    def formatter(self) -> ClaudeHookFormatter:
        return ClaudeHookFormatter()

    def resolve_project_dir(self) -> str:
        return (
            os.environ.get("AGENTLINT_PROJECT_DIR")
            or os.environ.get("CLAUDE_PROJECT_DIR")
            or os.getcwd()
        )

    def resolve_session_key(self) -> str:
        return (
            os.environ.get("AGENTLINT_SESSION_ID")
            or os.environ.get("CLAUDE_SESSION_ID")
            or f"pid-{os.getppid()}"
        )

    def translate_event(self, native_event: str) -> AgentEvent:
        try:
            return _CLAUDE_EVENT_MAP[native_event]
        except KeyError:
            raise ValueError(f"Unknown Claude event: {native_event}")

    def normalize_tool_name(self, native_tool: str) -> str:
        return _CLAUDE_TOOL_MAP.get(native_tool, NormalizedTool.UNKNOWN).value

    def build_rule_context(
        self,
        event: AgentEvent,
        raw_payload: dict[str, Any],
        project_dir: str,
        session_state: dict,
    ) -> RuleContext:
        tool_input = raw_payload.get("tool_input", {})
        return RuleContext(
            event=HookEvent.from_string(raw_payload.get("event", event.value)),
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
            agent_platform="claude",
        )

    def install_hooks(
        self,
        project_dir: str,
        scope: str = "project",
        dry_run: bool = False,
        cmd: str | None = None,
    ) -> None:
        """Install AgentLint hooks into Claude Code settings."""
        cmd = cmd or resolve_command()
        path = _settings_path(scope, project_dir)
        existing = read_json_config(path)

        settings = dict(existing or {})
        hooks_template = _build_hooks(cmd)
        hooks = dict(settings.get("hooks", {}))

        for event, our_entries in hooks_template.items():
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
        """Remove AgentLint hooks from Claude Code settings."""
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
