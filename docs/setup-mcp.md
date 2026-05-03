# Setup Guide: MCP (Model Context Protocol)

AgentLint exposes its rules engine as an MCP server.

## Installation

```bash
pip install agentlint[mcp]
```

Add to your MCP host configuration:

```json
{
  "mcpServers": {
    "agentlint": {
      "command": "agentlint-mcp",
      "args": [],
      "env": {
        "AGENTLINT_PROJECT_DIR": "/path/to/your/project"
      }
    }
  }
}
```

Or using `uvx` (no install):

```json
{
  "mcpServers": {
    "agentlint": {
      "command": "uvx",
      "args": ["agentlint[mcp]", "agentlint-mcp"],
      "env": {
        "AGENTLINT_PROJECT_DIR": "/path/to/your/project"
      }
    }
  }
}
```

## Tools

- `check_content(content, file_path, tool_name="Write", event="PreToolUse")` — pre-validate content
- `check_event(event, tool_name, tool_input, file_content=None)` — generic event checking
- `list_rules(pack=None)` — list all rules
- `get_config()` — get current configuration
- `get_session()` — get session state
- `suppress_rule(rule_id)` — suppress a warning rule

## Resources

- `agentlint://rules` — all rules with metadata
- `agentlint://config` — current configuration
- `agentlint://session` — current session state

## MCP Interceptor (Future)

When SEP-1763 (MCP Interceptor Framework) stabilizes, AgentLint will support transparent interception of all MCP tool calls without requiring the agent to proactively call `check_content`.
