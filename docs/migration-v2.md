# Migration Guide: v1.x → v2.0

AgentLint v2.0 is fully backward-compatible for existing Claude Code users. No action is required unless you want to use new platforms or features.

## What's New in v2.0

- **10 platform adapters** — Claude Code, Cursor, Kimi, Grok, Gemini, Codex, Continue, OpenAI Agents SDK, MCP, Generic HTTP
- **Unified `AgentEvent` taxonomy** — 17 normalized events that work across all platforms
- **`NormalizedTool` cross-platform mappings** — rules written once work everywhere
- **Auto-detection** — CLI automatically selects the right adapter from environment variables
- **Explicit adapter selection** — `agentlint setup <platform>` and `--adapter <platform>` flags

## For Existing Claude Code Users

**Nothing changes.** Your existing setup continues to work:

- `agentlint setup` still defaults to Claude Code
- `CLAUDE_PROJECT_DIR` and `CLAUDE_SESSION_ID` still work
- `HookEvent` enum values are unchanged
- All 17 hook events are still supported

If you run `agentlint setup` again, it will upgrade your hooks to include the new v2 marker field (for more reliable uninstall) but functionally behaves the same.

## Adding a Second Platform

If you use multiple AI agents (e.g., Claude Code + Cursor), install AgentLint for each:

```bash
# Claude Code (already installed)
agentlint setup claude

# Cursor (new)
agentlint setup cursor

# Kimi (new)
agentlint setup kimi
```

Each platform has its own config file, so installations are independent.

## New CLI Flags

```bash
# Explicitly select adapter
agentlint check --event PreToolUse --adapter grok

# Explicitly select output format
agentlint check --event PreToolUse --format gemini

# Setup for a specific platform
agentlint setup gemini

# Uninstall from a specific platform
agentlint uninstall gemini
```

## Environment Variables

New generic environment variables take precedence over platform-specific ones:

| Priority | Variable |
|----------|----------|
| 1st | `AGENTLINT_PROJECT_DIR` |
| 2nd | `CLAUDE_PROJECT_DIR` / `CURSOR_PROJECT_DIR` / etc. |
| 3rd | Current working directory |

## Adapter Auto-Detection Priority

When `--adapter` is not specified, the CLI auto-detects from environment variables:

1. `KIMI_SESSION_ID` → Kimi
2. `GROK_SESSION_ID` → Grok
3. `GEMINI_SESSION_ID` → Gemini
4. `CODEX_SESSION_ID` → Codex
5. `CONTINUE_SESSION_ID` → Continue
6. `CURSOR_SESSION_ID` → Cursor
7. `OPENAI_RUN_ID` → OpenAI Agents
8. `MCP_SESSION_ID` → MCP
9. Fallback → Claude Code

## Custom Rules

Custom rules written for v1.x work without changes. The `RuleContext` object now includes `agent_platform` (defaults to `"unknown"`) and `normalized_tool` for cross-platform compatibility, but existing rules that don't use these fields are unaffected.

## Deprecations

None. All v1.x APIs, config keys, and CLI commands remain supported.
