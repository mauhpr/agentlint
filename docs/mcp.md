# MCP Server Guide

AgentLint exposes its rules engine via the [Model Context Protocol](https://modelcontextprotocol.io), letting AI agents **pre-validate code before writing it**. This eliminates the block-retry loop where an agent writes code, gets blocked by a PreToolUse hook, then rewrites — often repeatedly.

## The problem

Without MCP, the feedback loop looks like this:

1. Agent writes `config.py` containing a secret → **blocked** by `no-secrets`
2. Agent rewrites without the secret → **blocked** by `max-file-size`
3. Agent splits the file → finally passes

Each retry costs tokens and time. With MCP, the agent can call `check_content` *before* writing, fix all violations in one pass, and succeed on the first attempt.

## Quickstart

### Install

```bash
pip install agentlint[mcp]
```

### Add to Claude Code settings

In `.claude/settings.json`:

```json
{
  "mcpServers": {
    "agentlint": {
      "command": "agentlint-mcp",
      "args": [],
      "env": {
        "CLAUDE_PROJECT_DIR": "/path/to/your/project"
      }
    }
  }
}
```

Or using `uvx` (no install needed):

```json
{
  "mcpServers": {
    "agentlint": {
      "command": "uvx",
      "args": ["agentlint[mcp]", "agentlint-mcp"],
      "env": {
        "CLAUDE_PROJECT_DIR": "/path/to/your/project"
      }
    }
  }
}
```

### Verify

Once configured, the agent can call the `check_content` tool to validate code.

## Tools

### `check_content`

Pre-validate content against agentlint rules. Returns a JSON list of violations.

| Parameter   | Type   | Default      | Description                                |
|-------------|--------|--------------|--------------------------------------------|
| `content`   | string | required     | The content to check                       |
| `file_path` | string | required     | Target file path (used for rule matching)  |
| `tool_name` | string | `"Write"`    | Tool type: `"Write"`, `"Edit"`, or `"Bash"` |
| `event`     | string | `"PreToolUse"` | Hook event: `"PreToolUse"` or `"PostToolUse"` |

**Returns:** JSON array of violation objects.

```json
[
  {
    "rule_id": "no-secrets",
    "message": "Possible secret detected: API key pattern",
    "severity": "error",
    "file_path": "config.py",
    "line": 3,
    "suggestion": "Use environment variables or a secrets manager"
  }
]
```

Each violation contains:

| Field        | Type        | Description                          |
|--------------|-------------|--------------------------------------|
| `rule_id`    | string      | Rule identifier (e.g. `no-secrets`)  |
| `message`    | string      | Human-readable description           |
| `severity`   | string      | `"error"`, `"warning"`, or `"info"`  |
| `file_path`  | string/null | File path if applicable              |
| `line`       | int/null    | Line number if applicable            |
| `suggestion` | string/null | Suggested fix if available           |

Empty array `[]` means the content passed all rules.

**Example — check for secrets:**

```
check_content(
  content='API_KEY = "sk_live_abc123def456ghi789"',
  file_path="config.py"
)
```

**Example — check a Bash command:**

```
check_content(
  content="rm -rf /",
  file_path="",
  tool_name="Bash"
)
```

### `list_rules`

List all available rules, optionally filtered by pack.

| Parameter | Type        | Default | Description              |
|-----------|-------------|---------|--------------------------|
| `pack`    | string/null | `null`  | Filter by pack name      |

**Returns:** JSON array of rule objects.

```json
[
  {
    "id": "no-secrets",
    "description": "Blocks writes containing API keys, tokens, passwords",
    "severity": "error",
    "events": ["PreToolUse"],
    "pack": "universal"
  }
]
```

### `get_config`

Get the current agentlint configuration.

**Returns:** JSON object with active config.

```json
{
  "severity": "standard",
  "packs": ["universal", "python"],
  "custom_rules_dir": null,
  "rules": {}
}
```

### `suppress_rule`

Suppress a warning rule for the rest of the session. ERROR-severity rules are accepted but silently ignored at evaluation time — the engine never suppresses ERRORs.

| Parameter | Type   | Default  | Description              |
|-----------|--------|----------|--------------------------|
| `rule_id` | string | required | Rule to suppress         |

**Returns:** JSON confirmation.

```json
{
  "suppressed": "drift-detector",
  "total_suppressed": 1
}
```

## Resources

The MCP server also exposes two resources:

- `agentlint://rules` — All rules with metadata (equivalent to `list_rules()`)
- `agentlint://config` — Current configuration (equivalent to `get_config()`)

## Workflow recipes

### Pre-validate before writing

The most common pattern — check content before `Write`:

1. Agent calls `check_content(content=code, file_path="target.py")`
2. If violations returned: fix them in memory, re-check
3. Once clean: write the file (passes PreToolUse hook on first try)

### Suppress noisy warnings

When a rule fires repeatedly and the agent has acknowledged it:

1. Agent calls `suppress_rule(rule_id="drift-detector")`
2. Subsequent evaluations skip that rule for this session

### Check Bash commands

Validate destructive commands before running them:

```
check_content(
  content="docker rm -f $(docker ps -aq)",
  file_path="",
  tool_name="Bash"
)
```

## Integration with hooks

The MCP server and hook system are complementary:

- **Hooks** are the enforcement layer — they run automatically on every tool call
- **MCP** is the advisory layer — agents call it proactively to avoid violations

When both are active, the agent can use MCP to pre-validate, reducing the number of times hooks need to block. The hooks still serve as a safety net for cases where the agent doesn't pre-check.

## Troubleshooting

**MCP server not starting:** Ensure `fastmcp` is installed (`pip install agentlint[mcp]`). The `agentlint-mcp` command requires the `mcp` extra.

**Rules not loading:** The server reads `agentlint.yml` from `CLAUDE_PROJECT_DIR`. Ensure the env var is set in your MCP server config.

**Empty violations but hook still blocks:** MCP and hooks run independently. Check that the `event` parameter matches (default is `PreToolUse`). Also verify you're checking the same content the agent will actually write.

**Monorepo support:** The MCP server respects `projects:` config. Pass the full file path in `file_path` and rules will resolve to the correct project-specific packs.
