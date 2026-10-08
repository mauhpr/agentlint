# MCP hosts

AgentLint ships an MCP server, `agentlint-mcp` (stdio transport), that lets any MCP host check content, patches and events before acting. This page covers host configuration only; tools and resources are documented in [MCP](../mcp.md).

The MCP server is advisory: the agent decides when to call it. For enforcement, also install the agent's hooks (see the other pages in this folder).

## Install

```bash
pip install "agentlint[mcp]"
```

This installs the `agentlint-mcp` command. To run it without installing, use `uvx --from "agentlint[mcp]" agentlint-mcp` as the command.

Every host needs the same three things: the command `agentlint-mcp`, no arguments, and `AGENTLINT_PROJECT_DIR` set to the project's absolute path. Hosts often start MCP servers from a different working directory, so do not rely on the current directory.

`agentlint setup mcp` writes nothing; it prints a config snippet. That snippet currently uses the path of the `agentlint` CLI as the command; replace it with `agentlint-mcp` (and use an absolute project path).

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

Ask the agent to call the `list_rules` tool, or to run `check_content` on `API_KEY = "sk_live_abc123def456ghi789"` with `file_path` `config.py`. It should return a `no-secrets` violation. Most hosts also list connected servers and their tools (for example, `/mcp` in Claude Code).

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
