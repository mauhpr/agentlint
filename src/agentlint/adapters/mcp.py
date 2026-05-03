"""MCP (Model Context Protocol) adapter for AgentLint.

Provides two integration modes:
1. MCP Server mode — exposes AgentLint as an MCP server (existing functionality)
2. MCP Interceptor mode — prepares for SEP-1763 interceptor framework
"""
from __future__ import annotations

import json
import os
from typing import Any

from agentlint.adapters.base import AgentAdapter
from agentlint.config import load_config
from agentlint.engine import Engine
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext, to_hook_event, to_agent_event
from agentlint.packs import load_custom_rules, load_rules


# Mapping from MCP tool event names to generic AgentEvent
_MCP_EVENT_MAP: dict[str, AgentEvent] = {
    "tools/call/request": AgentEvent.PRE_TOOL_USE,
    "tools/call/response": AgentEvent.POST_TOOL_USE,
    "prompts/get/request": AgentEvent.PRE_TOOL_USE,
    "resources/read/request": AgentEvent.PRE_TOOL_USE,
}


class MCPAdapter(AgentAdapter):
    """AgentAdapter implementation for MCP hosts.

    Mode 1 (active): MCP Server — provides check_content, list_rules, etc.
    Mode 2 (future): MCP Interceptor — intercepts tools/call requests.
    """

    @property
    def platform_name(self) -> str:
        return "mcp"

    @property
    def formatter(self):
        from agentlint.formats.plain_json import PlainJsonFormatter
        return PlainJsonFormatter()

    def resolve_project_dir(self) -> str:
        return (
            os.environ.get("AGENTLINT_PROJECT_DIR")
            or os.environ.get("CLAUDE_PROJECT_DIR")
            or os.getcwd()
        )

    def resolve_session_key(self) -> str:
        return (
            os.environ.get("AGENTLINT_SESSION_ID")
            or os.environ.get("MCP_SESSION_ID")
            or f"pid-{os.getppid()}"
        )

    def translate_event(self, native_event: str) -> AgentEvent:
        try:
            return _MCP_EVENT_MAP[native_event]
        except KeyError:
            # Fall back to generic parsing
            return AgentEvent.from_string(native_event)

    def normalize_tool_name(self, native_tool: str) -> str:
        """MCP tools use arbitrary names — normalize known ones."""
        # Strip MCP: prefix if present
        if native_tool.startswith("MCP:"):
            native_tool = native_tool[4:]
        mapping = {
            "write": NormalizedTool.FILE_WRITE,
            "edit": NormalizedTool.FILE_EDIT,
            "bash": NormalizedTool.SHELL,
            "shell": NormalizedTool.SHELL,
            "read": NormalizedTool.FILE_READ,
            "grep": NormalizedTool.SEARCH,
            "search": NormalizedTool.SEARCH,
            "web_fetch": NormalizedTool.WEB_FETCH,
            "web_search": NormalizedTool.WEB_SEARCH,
        }
        return mapping.get(native_tool.lower(), NormalizedTool.UNKNOWN).value

    def build_rule_context(
        self,
        event: AgentEvent,
        raw_payload: dict[str, Any],
        project_dir: str,
        session_state: dict,
    ) -> RuleContext:
        tool_input = raw_payload.get("tool_input", raw_payload.get("arguments", {}))
        return RuleContext(
            event=to_hook_event(raw_payload.get("event", event)),
            tool_name=raw_payload.get("tool_name", raw_payload.get("name", "")),
            tool_input=tool_input,
            project_dir=project_dir,
            config={},
            session_state=session_state,
            prompt=raw_payload.get("prompt"),
            agent_platform="mcp",
        )

    def install_hooks(
        self,
        project_dir: str,
        scope: str = "project",
        dry_run: bool = False,
        cmd: str | None = None,
    ) -> None:
        """Print MCP server configuration for various hosts."""
        import click
        cmd = cmd or "agentlint-mcp"
        click.echo("Add this to your MCP host configuration:")
        click.echo(json.dumps({
            "mcpServers": {
                "agentlint": {
                    "command": cmd,
                    "args": [],
                    "env": {
                        "AGENTLINT_PROJECT_DIR": project_dir,
                    },
                }
            }
        }, indent=2))

    def uninstall_hooks(
        self,
        project_dir: str,
        scope: str = "project",
    ) -> None:
        """No-op — MCP is configured via host settings, not project files."""
        pass

    def check_content(
        self,
        content: str,
        file_path: str,
        tool_name: str = "Write",
        event: str = "PreToolUse",
    ) -> list[dict[str, Any]]:
        """MCP server mode: check content against rules."""
        from agentlint.models import to_hook_event

        project_dir = self.resolve_project_dir()
        config = load_config(project_dir)

        # Resolve project-specific packs for monorepo support
        effective_packs = config.resolve_packs_for_file(file_path, project_dir)
        effective_config = config.with_packs(effective_packs)

        rules = load_rules(effective_packs)
        if config.custom_rules_dir:
            rules.extend(load_custom_rules(config.custom_rules_dir, project_dir))

        try:
            agent_event = AgentEvent.from_string(event)
        except ValueError:
            try:
                agent_event = to_agent_event(HookEvent.from_string(event))
            except ValueError as exc:
                return [{"error": str(exc)}]
        hook_event = to_hook_event(agent_event)

        tool_input = {"file_path": file_path, "content": content}
        if tool_name == "Bash":
            tool_input = {"command": content}

        context = RuleContext(
            event=hook_event,
            tool_name=tool_name,
            tool_input=tool_input,
            project_dir=project_dir,
            file_content=content if tool_name != "Bash" else None,
            config=effective_config.rules,
            agent_platform="mcp",
        )

        engine = Engine(config=effective_config, rules=rules)
        result = engine.evaluate(context)
        return [v.to_dict() for v in result.violations]

    def list_rules(self, pack: str | None = None) -> list[dict[str, Any]]:
        """MCP server mode: list all available rules."""
        from agentlint.packs import PACK_MODULES

        project_dir = self.resolve_project_dir()
        config = load_config(project_dir)
        all_rules = load_rules(list(PACK_MODULES.keys()))
        if config.custom_rules_dir:
            all_rules.extend(load_custom_rules(config.custom_rules_dir, project_dir))
        if pack:
            all_rules = [r for r in all_rules if r.pack == pack]
        return [
            {
                "id": r.id,
                "description": r.description,
                "severity": r.severity.value,
                "events": [e.value for e in r.events],
                "pack": r.pack,
            }
            for r in sorted(all_rules, key=lambda r: (r.pack, r.id))
        ]

    def get_config(self) -> dict[str, Any]:
        """MCP server mode: get current configuration."""
        config = load_config(self.resolve_project_dir())
        return {
            "severity": config.severity,
            "packs": config.packs,
            "custom_rules_dir": config.custom_rules_dir,
            "rules": config.rules,
        }
