"""Gemini CLI adapter for AgentLint.

Google Gemini CLI provides a native hooks system with 11 lifecycle events.
Configuration is done via JSON in .gemini/settings.json.

Reference: https://geminicli.com/docs/hooks/
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
from agentlint.formats.gemini_hooks import GeminiHookFormatter
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext, to_hook_event


# Mapping from Gemini native event names to generic AgentEvent
_GEMINI_EVENT_MAP: dict[str, AgentEvent] = {
    "SessionStart": AgentEvent.SESSION_START,
    "SessionEnd": AgentEvent.SESSION_END,
    "BeforeAgent": AgentEvent.USER_PROMPT,
    "AfterAgent": AgentEvent.STOP,
    "BeforeModel": AgentEvent.USER_PROMPT,
    "AfterModel": AgentEvent.NOTIFICATION,
    "BeforeToolSelection": AgentEvent.PRE_TOOL_USE,
    "BeforeTool": AgentEvent.PRE_TOOL_USE,
    "AfterTool": AgentEvent.POST_TOOL_USE,
    "PreCompress": AgentEvent.PRE_COMPACT,
    "Notification": AgentEvent.NOTIFICATION,
}

# Mapping from Gemini tool names to NormalizedTool
_GEMINI_TOOL_MAP: dict[str, NormalizedTool] = {
    "bash": NormalizedTool.SHELL,
    "write_file": NormalizedTool.FILE_WRITE,
    "replace": NormalizedTool.FILE_EDIT,
    "read_file": NormalizedTool.FILE_READ,
    "grep": NormalizedTool.SEARCH,
    "glob": NormalizedTool.SEARCH,
    "web_search": NormalizedTool.WEB_SEARCH,
    "web_fetch": NormalizedTool.WEB_FETCH,
}


def _build_hooks(cmd: str) -> dict:
    """Build the Gemini hooks configuration for settings.json."""
    return {
        "hooks": {
            "BeforeTool": [
                {
                    "matcher": "write_file|replace|bash",
                    "hooks": [
                        {
                            "name": "agentlint-pre",
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event BeforeTool --adapter gemini",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "AfterTool": [
                {
                    "matcher": "write_file|replace",
                    "hooks": [
                        {
                            "name": "agentlint-post",
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event AfterTool --adapter gemini",
                            "timeout": 10,
                        }
                    ],
                }
            ],
            "BeforeAgent": [
                {
                    "hooks": [
                        {
                            "name": "agentlint-prompt",
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event BeforeAgent --adapter gemini",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "AfterAgent": [
                {
                    "matcher": "*",
                    "hooks": [
                        {
                            "name": "agentlint-stop",
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event AfterAgent --adapter gemini",
                            "timeout": 30,
                        }
                    ],
                }
            ],
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "name": "agentlint-start",
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event SessionStart --adapter gemini",
                            "timeout": 5,
                        }
                    ],
                }
            ],
            "PreCompress": [
                {
                    "hooks": [
                        {
                            "name": "agentlint-compact",
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event PreCompress --adapter gemini",
                            "timeout": 5,
                        }
                    ],
                }
            ],
        }
    }


def _settings_path(scope: str, project_dir: str | None = None) -> Path:
    """Return the path to the Gemini settings file."""
    if scope == "user":
        return Path.home() / ".gemini" / "settings.json"
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ".gemini" / "settings.json"


class GeminiAdapter(AgentAdapter):
    """AgentAdapter implementation for Gemini CLI."""

    @property
    def platform_name(self) -> str:
        return "gemini"

    @property
    def formatter(self) -> GeminiHookFormatter:
        return GeminiHookFormatter()

    def resolve_project_dir(self) -> str:
        return (
            os.environ.get("AGENTLINT_PROJECT_DIR")
            or os.environ.get("GEMINI_PROJECT_DIR")
            or os.getcwd()
        )

    def resolve_session_key(self) -> str:
        return (
            os.environ.get("AGENTLINT_SESSION_ID")
            or os.environ.get("GEMINI_SESSION_ID")
            or f"pid-{os.getppid()}"
        )

    def translate_event(self, native_event: str) -> AgentEvent:
        try:
            return _GEMINI_EVENT_MAP[native_event]
        except KeyError:
            raise ValueError(f"Unknown Gemini event: {native_event}")

    def normalize_tool_name(self, native_tool: str) -> str:
        return _GEMINI_TOOL_MAP.get(native_tool, NormalizedTool.UNKNOWN).value

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
            agent_platform="gemini",
        )

    def install_hooks(
        self,
        project_dir: str,
        scope: str = "project",
        dry_run: bool = False,
        cmd: str | None = None,
    ) -> None:
        """Install AgentLint hooks into Gemini settings.json."""
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
        """Remove AgentLint hooks from Gemini settings."""
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
