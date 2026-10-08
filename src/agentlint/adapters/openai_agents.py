"""OpenAI Agents SDK adapter for AgentLint.

The OpenAI Agents SDK has no hook files; it checks function-tool calls with
tool input guardrails. This adapter builds such a guardrail around AgentLint.

Usage (requires ``pip install openai-agents``)::

    from agents import Agent
    from agents.decorators import tool

    from agentlint.adapters.openai_agents import OpenAIAgentsAdapter

    agentlint_shell = OpenAIAgentsAdapter().tool_input_guardrail("Bash")

    @tool(tool_input_guardrails=[agentlint_shell])
    def run_shell(command: str) -> str:
        ...

    agent = Agent(name="builder", tools=[run_shell])
"""

from __future__ import annotations

import os
from typing import Any

from agentlint.adapters.base import AgentAdapter
from agentlint.config import load_config
from agentlint.engine import Engine
from agentlint.models import (
    AgentEvent,
    HookEvent,
    NormalizedTool,
    RuleContext,
    Severity,
    to_hook_event,
)
from agentlint.packs import load_project_rules

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
        except KeyError as exc:
            raise ValueError(f"Unknown OpenAI Agents event: {native_event}") from exc

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

        click.echo("OpenAI Agents SDK uses tool guardrails, not hooks. No files were changed.")
        click.echo("Attach AgentLint to each function tool (requires `pip install openai-agents`):")
        click.echo("""
from agents import Agent
from agents.decorators import tool

from agentlint.adapters.openai_agents import OpenAIAgentsAdapter

agentlint_shell = OpenAIAgentsAdapter().tool_input_guardrail("Bash")


@tool(tool_input_guardrails=[agentlint_shell])
def run_shell(command: str) -> str:
    \"\"\"Run a shell command in the project.\"\"\"
    ...


agent = Agent(name="builder", tools=[run_shell])
""")
        click.echo(
            "Details: https://github.com/mauhpr/agentlint/blob/main/docs/agents/openai-agents.md"
        )

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
        from agentlint.adapters.normalize import canonical_tool_call

        project_dir = project_dir or self.resolve_project_dir()
        config = load_config(project_dir)
        rules = load_project_rules(config, project_dir)
        tool_name, tool_input = canonical_tool_call(self, tool_name, tool_input)

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

    def tool_input_guardrail(
        self,
        tool_name: str = "Bash",
        arguments: dict[str, str] | None = None,
        project_dir: str | None = None,
    ):
        """Build an OpenAI Agents SDK tool input guardrail that runs AgentLint.

        ``tool_name`` is what the tool does in AgentLint terms: ``Bash`` (runs a
        command), ``Write`` or ``Edit``. ``arguments`` maps AgentLint input keys
        to your tool's argument names when they differ, e.g.
        ``{"command": "cmd"}`` or ``{"file_path": "path", "content": "text"}``.
        When AgentLint finds an ERROR, the tool call is skipped and the reasons
        are returned to the model instead.
        """
        import json

        from agents import ToolGuardrailFunctionOutput
        from agents.decorators import tool_input_guardrail

        mapping = arguments or {}

        @tool_input_guardrail
        def agentlint_guardrail(data):
            raw = json.loads(data.context.tool_arguments or "{}")
            tool_input = dict(raw)
            for agentlint_key, tool_key in mapping.items():
                if tool_key in raw:
                    tool_input[agentlint_key] = raw[tool_key]
            result = self.evaluate_tool_call(tool_name, tool_input, project_dir)
            if result["tripwire_triggered"]:
                reasons = "\n".join(
                    f"[{v['rule_id']}] {v['message']}"
                    for v in result["violations"]
                    if v["severity"] == Severity.ERROR.value
                )
                return ToolGuardrailFunctionOutput.reject_content(reasons)
            return ToolGuardrailFunctionOutput.allow()

        return agentlint_guardrail

    def as_guardrail(self) -> dict[str, Any]:
        """Deprecated: returns a plain dict the OpenAI Agents SDK cannot use.

        Use :meth:`tool_input_guardrail` instead.
        """
        import warnings

        warnings.warn(
            "OpenAIAgentsAdapter.as_guardrail() is not usable with the OpenAI Agents SDK; "
            "use tool_input_guardrail() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return {
            "name": "agentlint",
            "description": "AgentLint guardrails for code quality and security",
            "type": "tool",
            "handler": self.evaluate_tool_call,
        }
