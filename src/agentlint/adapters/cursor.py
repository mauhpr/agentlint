"""Cursor IDE adapter for AgentLint."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agentlint.adapters._utils import (
    is_agentlint_flat_entry,
    read_json_config,
    resolve_command,
    write_json_config,
)
from agentlint.adapters.base import AgentAdapter
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext, to_hook_event


# Mapping from Cursor native event names to generic AgentEvent
_CURSOR_EVENT_MAP: dict[str, AgentEvent] = {
    "sessionStart": AgentEvent.SESSION_START,
    "sessionEnd": AgentEvent.SESSION_END,
    "preToolUse": AgentEvent.PRE_TOOL_USE,
    "postToolUse": AgentEvent.POST_TOOL_USE,
    "postToolUseFailure": AgentEvent.POST_TOOL_FAILURE,
    "subagentStart": AgentEvent.SUB_AGENT_START,
    "subagentStop": AgentEvent.SUB_AGENT_STOP,
    "beforeShellExecution": AgentEvent.PRE_TOOL_USE,
    "afterShellExecution": AgentEvent.POST_TOOL_USE,
    "beforeMCPExecution": AgentEvent.PRE_TOOL_USE,
    "afterMCPExecution": AgentEvent.POST_TOOL_USE,
    "beforeReadFile": AgentEvent.PRE_TOOL_USE,
    "afterFileEdit": AgentEvent.POST_TOOL_USE,
    "beforeSubmitPrompt": AgentEvent.USER_PROMPT,
    "preCompact": AgentEvent.PRE_COMPACT,
    "stop": AgentEvent.STOP,
    "afterAgentResponse": AgentEvent.NOTIFICATION,
    "afterAgentThought": AgentEvent.NOTIFICATION,
}

# Mapping from Cursor tool names to NormalizedTool
_CURSOR_TOOL_MAP: dict[str, NormalizedTool] = {
    "Write": NormalizedTool.FILE_WRITE,
    "Read": NormalizedTool.FILE_READ,
    "Shell": NormalizedTool.SHELL,
    "Grep": NormalizedTool.SEARCH,
    "Delete": NormalizedTool.FILE_WRITE,
    "Task": NormalizedTool.SUB_AGENT,
}


def _build_hooks(cmd: str) -> dict:
    """Build the Cursor hooks.json configuration."""
    return {
        "version": 1,
        "hooks": {
            "preToolUse": [
                {
                    "matcher": "Shell|Write|Delete",
                    "_agentlint": "v2",
                    "command": f"{cmd} check --event preToolUse --adapter cursor",
                    "timeout": 5,
                }
            ],
            "postToolUse": [
                {
                    "matcher": "Write|Delete",
                    "_agentlint": "v2",
                    "command": f"{cmd} check --event postToolUse --adapter cursor",
                    "timeout": 10,
                }
            ],
            "beforeShellExecution": [
                {
                    "_agentlint": "v2",
                    "command": f"{cmd} check --event beforeShellExecution --adapter cursor",
                    "timeout": 5,
                }
            ],
            "afterFileEdit": [
                {
                    "_agentlint": "v2",
                    "command": f"{cmd} check --event afterFileEdit --adapter cursor",
                    "timeout": 10,
                }
            ],
            "beforeSubmitPrompt": [
                {
                    "_agentlint": "v2",
                    "command": f"{cmd} check --event beforeSubmitPrompt --adapter cursor",
                    "timeout": 5,
                }
            ],
            "subagentStart": [
                {
                    "_agentlint": "v2",
                    "command": f"{cmd} check --event subagentStart --adapter cursor",
                    "timeout": 5,
                }
            ],
            "subagentStop": [
                {
                    "_agentlint": "v2",
                    "command": f"{cmd} check --event subagentStop --adapter cursor",
                    "timeout": 10,
                }
            ],
            "stop": [
                {
                    "_agentlint": "v2",
                    "command": f"{cmd} report --adapter cursor",
                    "timeout": 30,
                }
            ],
        }
    }


def _hooks_path(scope: str, project_dir: str | None = None) -> Path:
    """Return the path to the Cursor hooks file."""
    if scope == "user":
        return Path.home() / ".cursor" / "hooks.json"
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ".cursor" / "hooks.json"


class CursorAdapter(AgentAdapter):
    """AgentAdapter implementation for Cursor IDE."""

    @property
    def platform_name(self) -> str:
        return "cursor"

    @property
    def formatter(self):
        from agentlint.formats.cursor_hooks import CursorHookFormatter
        return CursorHookFormatter()

    def resolve_project_dir(self) -> str:
        return (
            os.environ.get("AGENTLINT_PROJECT_DIR")
            or os.environ.get("CURSOR_PROJECT_DIR")
            or os.getcwd()
        )

    def resolve_session_key(self) -> str:
        return (
            os.environ.get("AGENTLINT_SESSION_ID")
            or os.environ.get("CURSOR_SESSION_ID")
            or f"pid-{os.getppid()}"
        )

    def translate_event(self, native_event: str) -> AgentEvent:
        try:
            return _CURSOR_EVENT_MAP[native_event]
        except KeyError:
            raise ValueError(f"Unknown Cursor event: {native_event}")

    def normalize_tool_name(self, native_tool: str) -> str:
        return _CURSOR_TOOL_MAP.get(native_tool, NormalizedTool.UNKNOWN).value

    def build_rule_context(
        self,
        event: AgentEvent,
        raw_payload: dict[str, Any],
        project_dir: str,
        session_state: dict,
    ) -> RuleContext:
        tool_input = raw_payload.get("tool_input", {})
        # Cursor passes tool_input directly; some events have different shapes
        return RuleContext(
            event=to_hook_event(raw_payload.get("event", event)),
            tool_name=raw_payload.get("tool_name", ""),
            tool_input=tool_input,
            project_dir=project_dir,
            config={},
            session_state=session_state,
            prompt=raw_payload.get("prompt"),
            subagent_output=raw_payload.get("subagent_output") or raw_payload.get("summary"),
            notification_type=raw_payload.get("notification_type"),
            compact_source=raw_payload.get("compact_source"),
            agent_transcript_path=raw_payload.get("agent_transcript_path"),
            agent_type=raw_payload.get("agent_type") or raw_payload.get("subagent_type"),
            agent_id=raw_payload.get("agent_id"),
            agent_platform="cursor",
        )

    def install_hooks(
        self,
        project_dir: str,
        scope: str = "project",
        dry_run: bool = False,
        cmd: str | None = None,
    ) -> None:
        """Install AgentLint hooks into Cursor hooks.json."""
        cmd = cmd or resolve_command()
        path = _hooks_path(scope, project_dir)
        existing = read_json_config(path)

        config = dict(existing or {})
        our_hooks = _build_hooks(cmd)

        # Merge version
        config["version"] = 1

        # Merge hooks
        hooks = dict(config.get("hooks", {}))
        for event, our_entries in our_hooks["hooks"].items():
            current = list(hooks.get(event, []))
            current = [e for e in current if not is_agentlint_flat_entry(e)]
            if isinstance(our_entries, list):
                current.extend(our_entries)
            else:
                current.append(our_entries)
            hooks[event] = current

        config["hooks"] = hooks

        if dry_run:
            import click
            click.echo(f"\nDry run — would write to {path}:")
            click.echo(json.dumps(config, indent=2))
            return

        write_json_config(path, config)

    def uninstall_hooks(
        self,
        project_dir: str,
        scope: str = "project",
    ) -> None:
        """Remove AgentLint hooks from Cursor hooks.json."""
        path = _hooks_path(scope, project_dir)
        existing = read_json_config(path)
        if existing is None:
            return  # Corrupted file — don't touch it
        config = dict(existing)
        hooks = dict(config.get("hooks", {}))

        for event in list(hooks):
            if isinstance(hooks[event], list):
                filtered = [e for e in hooks[event] if not is_agentlint_flat_entry(e)]
                if filtered:
                    hooks[event] = filtered
                else:
                    del hooks[event]
            elif is_agentlint_flat_entry(hooks[event]):
                del hooks[event]

        if hooks:
            config["hooks"] = hooks
        else:
            config.pop("hooks", None)

        # Delete file if config is empty or only contains version
        if not config or set(config.keys()) <= {"version"}:
            path.unlink(missing_ok=True)
        else:
            write_json_config(path, config)
