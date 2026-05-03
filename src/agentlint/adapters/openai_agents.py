"""OpenAI Agents SDK adapter for AgentLint.

This adapter integrates AgentLint with the OpenAI Agents SDK guardrails system.
Instead of hooks, OpenAI Agents uses guardrail functions that wrap tool calls.

Usage:
    from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
    from openai.agents import Agent, Guardrail

    adapter = OpenAIAgentsAdapter()
    agent = Agent(
        name="my-agent",
        tools=[...],
        guardrails=[adapter.as_guardrail()],
    )
"""
from __future__ import annotations

import os
from typing import Any

from agentlint.adapters.base import AgentAdapter
from agentlint.config import load_config
from agentlint.engine import Engine
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext, Severity, to_hook_event
from agentlint.packs import load_custom_rules, load_rules


# Mapping from OpenAI Agents SDK event names to generic AgentEvent
_OPENAI_EVENT_MAP: dict[str, AgentEvent] = {
    "beforeToolCall": AgentEvent.PRE_TOOL_USE,
    "afterToolCall": AgentEvent.POST_TOOL_USE,
    "onHandoff": AgentEvent.SUB_AGENT_START,
    "onComplete": AgentEvent.SESSION_END,
    "onStart": AgentEvent.SESSION_START,
}

# OpenAI Agents SDK uses function names as tool identifiers
_OPENAI_TOOL_MAP: dict[str, NormalizedTool] = {
    "file_write": NormalizedTool.FILE_WRITE,
    "file_edit": NormalizedTool.FILE_EDIT,
    "shell": NormalizedTool.SHELL,
    "file_read": NormalizedTool.FILE_READ,
    "search": NormalizedTool.SEARCH,
    "web_fetch": NormalizedTool.WEB_FETCH,
    "web_search": NormalizedTool.WEB_SEARCH,
    "handoff": NormalizedTool.SUB_AGENT,
}


class OpenAIAgentsAdapter(AgentAdapter):
    """AgentAdapter implementation for OpenAI Agents SDK.

    Provides both direct evaluation and a guardrail-compatible interface
    for integration with OpenAI Agents SDK.
    """

    @property
    def platform_name(self) -> str:
        return "openai"

    @property
    def formatter(self):
        from agentlint.formats.plain_json import PlainJsonFormatter
        return PlainJsonFormatter()

    def resolve_project_dir(self) -> str:
        return (
            os.environ.get("AGENTLINT_PROJECT_DIR")
            or os.environ.get("OPENAI_PROJECT_DIR")
            or os.getcwd()
        )

    def resolve_session_key(self) -> str:
        return (
            os.environ.get("AGENTLINT_SESSION_ID")
            or os.environ.get("OPENAI_RUN_ID")
            or os.environ.get("OPENAI_THREAD_ID")
            or f"pid-{os.getppid()}"
        )

    def translate_event(self, native_event: str) -> AgentEvent:
        try:
            return _OPENAI_EVENT_MAP[native_event]
        except KeyError:
            raise ValueError(f"Unknown OpenAI Agents event: {native_event}")

    def normalize_tool_name(self, native_tool: str) -> str:
        return _OPENAI_TOOL_MAP.get(native_tool, NormalizedTool.UNKNOWN).value

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
            tool_name=raw_payload.get("tool_name", raw_payload.get("function_name", "")),
            tool_input=tool_input,
            project_dir=project_dir,
            config={},
            session_state=session_state,
            prompt=raw_payload.get("prompt"),
            agent_platform="openai",
        )

    def install_hooks(
        self,
        project_dir: str,
        scope: str = "project",
        dry_run: bool = False,
        cmd: str | None = None,
    ) -> None:
        """OpenAI Agents SDK does not use hooks — guardrails are code-based.

        Prints a setup code snippet instead.
        """
        import click
        click.echo("OpenAI Agents SDK uses guardrails, not hooks.")
        click.echo("Add the guardrail to your agent definition:")
        click.echo("""
from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
from openai.agents import Agent

adapter = OpenAIAgentsAdapter()
agent = Agent(
    name="my-agent",
    tools=[...],
    guardrails=[adapter.as_guardrail()],
)
""")

    def uninstall_hooks(
        self,
        project_dir: str,
        scope: str = "project",
    ) -> None:
        """No-op — guardrails are code-based, not file-based."""
        pass

    def evaluate_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        project_dir: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate a single tool call against AgentLint rules.

        Returns a guardrail-compatible result dict.
        """
        project_dir = project_dir or self.resolve_project_dir()
        config = load_config(project_dir)
        rules = load_rules(config.packs)
        if config.custom_rules_dir:
            rules.extend(load_custom_rules(config.custom_rules_dir, project_dir))

        context = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name=tool_name,
            tool_input=tool_input,
            project_dir=project_dir,
            file_content=tool_input.get("content") if isinstance(tool_input, dict) else None,
            config=config.rules,
            agent_platform="openai",
        )

        engine = Engine(config=config, rules=rules)
        result = engine.evaluate(context)

        errors = [v for v in result.violations if v.severity == Severity.ERROR]
        warnings = [v for v in result.violations if v.severity == Severity.WARNING]

        return {
            "tripwire_triggered": len(errors) > 0,
            "violations": [v.to_dict() for v in result.violations],
            "blocked_count": len(errors),
            "warning_count": len(warnings),
        }

    def as_guardrail(self) -> dict[str, Any]:
        """Return a guardrail dict for OpenAI Agents SDK integration.

        This is a simplified interface. Full integration requires the
        openai-agents SDK to be installed.
        """
        return {
            "name": "agentlint",
            "description": "AgentLint guardrails for code quality and security",
            "type": "tool",
            "handler": self.evaluate_tool_call,
        }
