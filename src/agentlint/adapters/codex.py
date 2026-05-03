"""Codex CLI adapter for AgentLint.

OpenAI Codex CLI provides a native hooks system with 6 lifecycle events.
Configuration is done via JSON in ~/.codex/hooks.json (requires codex_hooks = true in config.toml).

Reference: https://developers.openai.com/codex/hooks
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


# Mapping from Codex native event names to generic AgentEvent
_CODEX_EVENT_MAP: dict[str, AgentEvent] = {
    "PreToolUse": AgentEvent.PRE_TOOL_USE,
    "PostToolUse": AgentEvent.POST_TOOL_USE,
    "PostToolUseFailure": AgentEvent.POST_TOOL_FAILURE,
    "UserPromptSubmit": AgentEvent.USER_PROMPT,
    "Stop": AgentEvent.STOP,
    "SessionStart": AgentEvent.SESSION_START,
    "SessionEnd": AgentEvent.SESSION_END,
    "AfterAgent": AgentEvent.STOP,
    "AfterToolUse": AgentEvent.POST_TOOL_USE,
}

# Mapping from Codex tool names to NormalizedTool
_CODEX_TOOL_MAP: dict[str, NormalizedTool] = {
    "Bash": NormalizedTool.SHELL,
    "apply_patch": NormalizedTool.FILE_EDIT,
    "Read": NormalizedTool.FILE_READ,
    "WebSearch": NormalizedTool.WEB_SEARCH,
    "WebFetch": NormalizedTool.WEB_FETCH,
}


def _build_hooks(cmd: str) -> dict:
    """Build the Codex hooks configuration for hooks.json.

    Note: Codex uses 30-second timeouts for all events because its hook
    system is experimental and may have higher latency than other platforms.
    """
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "^Bash$",
                    "hooks": [
                        {
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event PreToolUse --adapter codex",
                            "timeout": 30,
                            "statusMessage": "Checking Bash command",
                        }
                    ],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "^Bash$",
                    "hooks": [
                        {
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event PostToolUse --adapter codex",
                            "timeout": 30,
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
                            "command": f"{cmd} check --event UserPromptSubmit --adapter codex",
                            "timeout": 30,
                        }
                    ],
                }
            ],
            "SessionStart": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "_agentlint": "v2",
                            "command": f"{cmd} check --event SessionStart --adapter codex",
                            "timeout": 30,
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
                            "command": f"{cmd} report --adapter codex",
                            "timeout": 30,
                        }
                    ],
                }
            ],
        }
    }


def _hooks_path(scope: str, project_dir: str | None = None) -> Path:
    """Return the path to the Codex hooks file."""
    if scope == "user":
        return Path.home() / ".codex" / "hooks.json"
    base = Path(project_dir) if project_dir else Path.cwd()
    # Codex prefers git-root-based paths for repo-local hooks
    return base / ".codex" / "hooks.json"


class CodexAdapter(AgentAdapter):
    """AgentAdapter implementation for Codex CLI.

    Note: Codex PreToolUse currently only reliably intercepts Bash tool calls.
    apply_patch edits and MCP tool calls have intermittent hook coverage.
    """

    @property
    def platform_name(self) -> str:
        return "codex"

    @property
    def formatter(self) -> ClaudeHookFormatter:
        return ClaudeHookFormatter()

    def resolve_project_dir(self) -> str:
        return (
            os.environ.get("AGENTLINT_PROJECT_DIR")
            or os.environ.get("CODEX_PROJECT_DIR")
            or os.getcwd()
        )

    def resolve_session_key(self) -> str:
        return (
            os.environ.get("AGENTLINT_SESSION_ID")
            or os.environ.get("CODEX_SESSION_ID")
            or f"pid-{os.getppid()}"
        )

    def translate_event(self, native_event: str) -> AgentEvent:
        try:
            return _CODEX_EVENT_MAP[native_event]
        except KeyError:
            raise ValueError(f"Unknown Codex event: {native_event}")

    def normalize_tool_name(self, native_tool: str) -> str:
        return _CODEX_TOOL_MAP.get(native_tool, NormalizedTool.UNKNOWN).value

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
            agent_platform="codex",
        )

    def install_hooks(
        self,
        project_dir: str,
        scope: str = "project",
        dry_run: bool = False,
        cmd: str | None = None,
    ) -> None:
        """Install AgentLint hooks into Codex hooks.json."""
        cmd = cmd or resolve_command()
        path = _hooks_path(scope, project_dir)
        existing = read_json_config(path)

        config = dict(existing or {})
        hooks_template = _build_hooks(cmd)

        hooks = dict(config.get("hooks", {}))
        for event, our_entries in hooks_template["hooks"].items():
            current = list(hooks.get(event, []))
            current = [e for e in current if not is_agentlint_nested_entry(e)]
            current.extend(our_entries)
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
        """Remove AgentLint hooks from Codex hooks.json."""
        path = _hooks_path(scope, project_dir)
        existing = read_json_config(path)
        if existing is None:
            return  # Corrupted file — don't touch it
        config = dict(existing)
        hooks = dict(config.get("hooks", {}))

        for event in list(hooks):
            filtered = [e for e in hooks[event] if not is_agentlint_nested_entry(e)]
            if filtered:
                hooks[event] = filtered
            else:
                del hooks[event]

        if hooks:
            config["hooks"] = hooks
        else:
            config.pop("hooks", None)

        if config:
            write_json_config(path, config)
        elif path.exists():
            path.unlink(missing_ok=True)
