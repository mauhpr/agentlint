"""Generic HTTP/webhook adapter for AgentLint.

This adapter accepts normalized events and tool names via HTTP/webhook,
making AgentLint usable with custom agent frameworks, CI pipelines,
and enterprise integrations.

Configuration in agentlint.yml:
    generic:
      webhook_url: https://my-ci.example.com/agentlint
      headers:
        Authorization: Bearer ${TOKEN}
"""
from __future__ import annotations

import os
from typing import Any

from agentlint.adapters.base import AgentAdapter
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext, to_hook_event


class GenericAdapter(AgentAdapter):
    """AgentAdapter implementation for generic HTTP/webhook integrations.

    Expects normalized event names and tool names in the payload.
    """

    @property
    def platform_name(self) -> str:
        return "generic"

    @property
    def formatter(self):
        from agentlint.formats.plain_json import PlainJsonFormatter
        return PlainJsonFormatter()

    def resolve_project_dir(self) -> str:
        return (
            os.environ.get("AGENTLINT_PROJECT_DIR")
            or os.getcwd()
        )

    def resolve_session_key(self) -> str:
        return (
            os.environ.get("AGENTLINT_SESSION_ID")
            or f"pid-{os.getppid()}"
        )

    def translate_event(self, native_event: str) -> AgentEvent:
        """Accepts both generic event values and AgentEvent member names."""
        try:
            return AgentEvent.from_string(native_event)
        except ValueError:
            # Try matching against enum member names for convenience
            for member in AgentEvent:
                if member.name == native_event:
                    return member
            raise ValueError(f"Unknown generic event: {native_event}")

    def normalize_tool_name(self, native_tool: str) -> str:
        """Accepts NormalizedTool values directly."""
        try:
            return NormalizedTool(native_tool).value
        except ValueError:
            return NormalizedTool.UNKNOWN.value

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
            subagent_output=raw_payload.get("subagent_output"),
            notification_type=raw_payload.get("notification_type"),
            agent_transcript_path=raw_payload.get("agent_transcript_path"),
            agent_type=raw_payload.get("agent_type"),
            agent_id=raw_payload.get("agent_id"),
            agent_platform="generic",
        )

    def install_hooks(
        self,
        project_dir: str,
        scope: str = "project",
        dry_run: bool = False,
        cmd: str | None = None,
    ) -> None:
        """Generic adapter does not install hooks — print configuration example."""
        import click
        click.echo("Generic adapter configured via agentlint.yml:")
        click.echo("""
generic:
  webhook_url: https://your-webhook.example.com/agentlint
  headers:
    Authorization: Bearer ${TOKEN}
""")

    def uninstall_hooks(
        self,
        project_dir: str,
        scope: str = "project",
    ) -> None:
        """No-op for generic adapter."""
        pass
