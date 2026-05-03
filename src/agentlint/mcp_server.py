"""AgentLint MCP server — expose rules and checking via Model Context Protocol.

Install with: pip install agentlint[mcp]
Run with: agentlint-mcp (stdio transport)
"""
from __future__ import annotations

import json

from agentlint.adapters.mcp import MCPAdapter
from agentlint.session import load_session, save_session

try:
    from fastmcp import FastMCP
except ImportError:
    raise ImportError(
        "FastMCP is required for the MCP server. "
        "Install with: pip install agentlint[mcp]"
    )

mcp = FastMCP("agentlint")
_adapter = MCPAdapter()


@mcp.tool
def check_content(
    content: str,
    file_path: str,
    tool_name: str = "Write",
    event: str = "PreToolUse",
) -> str:
    """Check content against agentlint rules. Returns JSON list of violations.

    Use this to pre-validate code before writing it, avoiding the
    block-then-retry loop from PreToolUse hooks. Set tool_name="Bash"
    and pass the command as content to pre-check Bash commands.
    """
    violations = _adapter.check_content(content, file_path, tool_name, event)
    return json.dumps(violations)


@mcp.tool
def check_event(
    event: str,
    tool_name: str,
    tool_input: dict,
    file_content: str | None = None,
) -> str:
    """Check a generic event against agentlint rules. Returns JSON list of violations.

    Supports normalized event names (pre_tool_use, post_tool_use, etc.)
    and any agent framework's tool input shape.
    """
    from agentlint.config import load_config
    from agentlint.engine import Engine
    from agentlint.models import AgentEvent, RuleContext, to_hook_event
    from agentlint.packs import load_custom_rules, load_rules

    project_dir = _adapter.resolve_project_dir()
    config = load_config(project_dir)
    rules = load_rules(config.packs)
    if config.custom_rules_dir:
        rules.extend(load_custom_rules(config.custom_rules_dir, project_dir))

    agent_event = AgentEvent.from_string(event)
    hook_event = to_hook_event(agent_event)

    context = RuleContext(
        event=hook_event,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir=project_dir,
        file_content=file_content,
        config=config.rules,
        agent_platform="mcp",
    )

    engine = Engine(config=config, rules=rules)
    result = engine.evaluate(context)
    return json.dumps([v.to_dict() for v in result.violations])


@mcp.tool
def list_rules(pack: str | None = None) -> str:
    """List all available agentlint rules, optionally filtered by pack. Returns JSON."""
    rules = _adapter.list_rules(pack)
    return json.dumps(rules)


@mcp.tool
def get_config() -> str:
    """Get the current agentlint configuration. Returns JSON."""
    config = _adapter.get_config()
    return json.dumps(config)


@mcp.tool
def get_session() -> str:
    """Get the current agentlint session state. Returns JSON."""
    session_state = load_session(key=_adapter.resolve_session_key())
    return json.dumps(session_state)


@mcp.tool
def suppress_rule(rule_id: str) -> str:
    """Suppress a warning rule for the rest of the session.

    ERRORs are accepted but silently ignored at evaluation time —
    the engine never suppresses ERROR-severity violations regardless
    of the suppressed_rules list.
    """
    session_state = load_session(key=_adapter.resolve_session_key())
    suppressed = session_state.setdefault("suppressed_rules", [])
    if rule_id not in suppressed:
        suppressed.append(rule_id)
    save_session(session_state, key=_adapter.resolve_session_key())
    return json.dumps({"suppressed": rule_id, "total_suppressed": len(suppressed)})


@mcp.resource("agentlint://rules")
def rules_resource() -> str:
    """All agentlint rules with metadata."""
    return list_rules()


@mcp.resource("agentlint://config")
def config_resource() -> str:
    """Current agentlint configuration."""
    return get_config()


@mcp.resource("agentlint://session")
def session_resource() -> str:
    """Current agentlint session state."""
    return get_session()


def run():
    """Entry point for agentlint-mcp script."""
    mcp.run()


if __name__ == "__main__":
    run()
