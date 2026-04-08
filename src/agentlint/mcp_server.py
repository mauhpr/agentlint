"""AgentLint MCP server — expose rules and checking via Model Context Protocol.

Install with: pip install agentlint[mcp]
Run with: agentlint-mcp (stdio transport)
"""
from __future__ import annotations

import json
import os

try:
    from fastmcp import FastMCP
except ImportError:
    raise ImportError(
        "FastMCP is required for the MCP server. "
        "Install with: pip install agentlint[mcp]"
    )

from agentlint.config import AgentLintConfig, load_config
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext
from agentlint.packs import PACK_MODULES, load_custom_rules, load_rules

mcp = FastMCP("agentlint")


def _project_dir() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def _load_engine() -> tuple[Engine, AgentLintConfig]:
    project_dir = _project_dir()
    config = load_config(project_dir)
    rules = load_rules(config.packs)
    if config.custom_rules_dir:
        rules.extend(load_custom_rules(config.custom_rules_dir, project_dir))
    return Engine(config=config, rules=rules), config


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
    try:
        hook_event = HookEvent.from_string(event)
    except ValueError:
        return json.dumps([{"error": f"Unknown event: {event}. Use PreToolUse or PostToolUse."}])

    project_dir = _project_dir()
    engine, config = _load_engine()
    tool_input = {"file_path": file_path, "content": content}
    if tool_name == "Bash":
        tool_input = {"command": content}
    context = RuleContext(
        event=hook_event,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir=project_dir,
        file_content=content if tool_name != "Bash" else None,
        config=config.rules,
    )
    result = engine.evaluate(context)
    return json.dumps([v.to_dict() for v in result.violations])


@mcp.tool
def list_rules(pack: str | None = None) -> str:
    """List all available agentlint rules, optionally filtered by pack. Returns JSON."""
    project_dir = _project_dir()
    config = load_config(project_dir)
    all_rules = load_rules(list(PACK_MODULES.keys()))
    if config.custom_rules_dir:
        all_rules.extend(load_custom_rules(config.custom_rules_dir, project_dir))
    if pack:
        all_rules = [r for r in all_rules if r.pack == pack]
    data = [
        {
            "id": r.id,
            "description": r.description,
            "severity": r.severity.value,
            "events": [e.value for e in r.events],
            "pack": r.pack,
        }
        for r in sorted(all_rules, key=lambda r: (r.pack, r.id))
    ]
    return json.dumps(data)


@mcp.tool
def get_config() -> str:
    """Get the current agentlint configuration. Returns JSON."""
    config = load_config(_project_dir())
    return json.dumps({
        "severity": config.severity,
        "packs": config.packs,
        "custom_rules_dir": config.custom_rules_dir,
        "rules": config.rules,
    })


@mcp.resource("agentlint://rules")
def rules_resource() -> str:
    """All agentlint rules with metadata."""
    return list_rules()


@mcp.resource("agentlint://config")
def config_resource() -> str:
    """Current agentlint configuration."""
    return get_config()


def run():
    """Entry point for agentlint-mcp script."""
    mcp.run()


if __name__ == "__main__":
    run()
