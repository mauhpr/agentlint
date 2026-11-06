---
description: Configure AgentLint's advisory MCP server in your host and verify a data-only rule check.
---

# MCP hosts

The read-only [`get_activity()` tool](../mcp.md#get_activity) exposes worktree-scoped observations from native hooks or the [shared host activity API](../diagnostics.md#host-activity-and-pending-approvals). MCP cannot automatically observe another tool's approval queue; absent telemetry is unknown.

AgentLint ships an MCP server, `agentlint-mcp` (stdio transport), that lets any MCP host check content, patches and events before acting. This page covers host configuration only; tools and resources are documented in [MCP](../mcp.md).

The MCP server is advisory: the agent decides when to call it. For enforcement, also install the agent's hooks (see the other pages in this folder).

Use MCP to ask for a check before a real edit, inspect available rules, or preview a patch. A host connection does not turn these checks into automatic interception. See [Coverage and limits](../coverage.md).

## Install

```bash
pip install "agentlint[mcp]"
```

This installs the `agentlint-mcp` command. To run it without installing, use `uvx --from "agentlint[mcp]" agentlint-mcp` as the command.

Every host needs the same three things: the command `agentlint-mcp`, no arguments, and `AGENTLINT_PROJECT_DIR` set to the project's absolute path. Hosts often start MCP servers from a different working directory, so do not rely on the current directory.

`agentlint setup mcp` writes nothing; it prints a config snippet with the `agentlint-mcp` command (the binary next to your `agentlint`, if found) and the absolute project path.

### Claude Code

Project-scoped `.mcp.json` in the repository root:

```json
{
  "mcpServers": {
    "agentlint": {
      "command": "agentlint-mcp",
      "args": [],
      "env": { "AGENTLINT_PROJECT_DIR": "/path/to/your/project" }
    }
  }
}
```

### Claude Desktop

Add the same `mcpServers` entry to `claude_desktop_config.json` (on macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`) and restart the app.

### Cursor

Add the same `mcpServers` entry to `.cursor/mcp.json` (project) or `~/.cursor/mcp.json` (user).

### Gemini CLI

Add the same `mcpServers` entry to `.gemini/settings.json` or `~/.gemini/settings.json`.

### Codex CLI

In `~/.codex/config.toml`:

```toml
[mcp_servers.agentlint]
command = "agentlint-mcp"
args = []
env = { AGENTLINT_PROJECT_DIR = "/path/to/your/project" }
```

### Using uvx

Replace the command and arguments in any of the JSON examples:

```json
"command": "uvx",
"args": ["--from", "agentlint[mcp]", "agentlint-mcp"]
```

## Verify

Ask the agent to call `list_rules`, then evaluate a proposed environment-file write:

```json
{
  "content": "# proposed local settings\n",
  "file_path": ".env",
  "tool_name": "Write"
}
```

Send those arguments to `check_content`. With the default universal rules, it returns a `no-env-commit` ERROR. Changing `file_path` to `.env.example` avoids that rule. This checks data without writing either file; other configured rules still apply.

Most hosts also list connected servers and their tools (for example, `/mcp` in Claude Code).

`agentlint status` does not report MCP connections; it only covers hook-based agents.

## What is checked

Whatever the agent sends to the server's tools: file content, Bash commands, Codex patches and generic events. See [MCP](../mcp.md) for each tool.

## Configuration notes

- Project directory: `AGENTLINT_PROJECT_DIR`, then `CLAUDE_PROJECT_DIR`, then the server's working directory. The server reads `agentlint.yml` from there.
- Session key (used by `get_session` and `suppress_rule`): `AGENTLINT_SESSION_ID`, then `MCP_SESSION_ID`, then the parent process ID. To share suppressions with the agent's hooks, both must resolve to the same key; set `AGENTLINT_SESSION_ID` explicitly if they do not.

## Uninstall

Remove the `agentlint` entry from the host's MCP configuration. `agentlint uninstall mcp` is a no-op.

## Troubleshooting

- **Server fails to start with an ImportError about FastMCP:** install the extra: `pip install "agentlint[mcp]"`.
- **Wrong rules or packs:** `AGENTLINT_PROJECT_DIR` is missing or relative. Call `get_config` to see which config the server loaded.
- General issues: [Diagnostics](../diagnostics.md). Tool reference: [MCP](../mcp.md).
