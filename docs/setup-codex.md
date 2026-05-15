# Setup Guide: Codex CLI (OpenAI)

AgentLint supports Codex CLI via native hooks in `~/.codex/hooks.json`.

## Installation

```bash
agentlint setup codex
```

This creates `.codex/hooks.json` in your project root with hooks for:

- `PreToolUse` — blocks Bash commands (secrets, destructive commands, etc.)
- `PostToolUse` — checks Bash command quality after execution
- `UserPromptSubmit` — prompt-level rule evaluation
- `SessionStart` — session initialization
- `Stop` — session summary report

Codex also requires native hooks to be enabled globally. `agentlint setup codex`
updates `~/.codex/config.toml` for you by adding the flag under `[features]`:

```toml
[features]
codex_hooks = true
```

Do not append `codex_hooks = true` to the end of `config.toml` manually. TOML
assigns bare keys to the most recent table, so appending after a section such as
`[tui.model_availability_nux]` can make Codex fail to load its config.

Restart Codex from the terminal where your AgentLint/AgentChute environment
variables are set:

```bash
codex
```

For AgentChute local testing, set the API URL before starting Codex:

```bash
export AGENTCHUTE_API_URL=http://localhost:8000/v1
export AGENTCHUTE_LICENSE_KEY=ac_team_...
export AGENTCHUTE_ENABLED=true
```

## Important: Codex Hook Coverage

Codex's PreToolUse hook currently only reliably intercepts **Bash tool calls**. Coverage for `apply_patch` edits and MCP tool calls is intermittent and depends on the Codex CLI version. This is a known upstream limitation.

## Hook Format

Codex uses a JSON-based hook protocol:

- **Exit 0** — success; JSON output parsed
- **Exit 2** — block the action

Blocking output:
```json
{
  "hookSpecificOutput": {
    "permissionDecision": "deny",
    "permissionDecisionReason": "[no-secrets] Possible secret token detected"
  }
}
```

Codex also supports a legacy `decision: "block"` format; AgentLint uses the modern `permissionDecision` protocol by default.

## Global Installation

```bash
agentlint setup codex --global
```

Installs to `~/.codex/hooks.json` (affects all projects).

## Uninstall

```bash
agentlint uninstall codex
```

Removes only AgentLint hooks; preserves any other custom hooks you have configured.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `CODEX_PROJECT_DIR` | Project directory override |
| `CODEX_SESSION_ID` | Session ID for state tracking |
| `AGENTLINT_PROJECT_DIR` | Generic project directory (takes precedence) |
| `AGENTLINT_SESSION_ID` | Generic session ID (takes precedence) |

## Troubleshooting

**Hooks not firing for Write/Edit?**
- This is a known Codex CLI limitation. PreToolUse hooks for `apply_patch` and MCP tools have intermittent coverage
- Ensure your Codex CLI is up to date; hook support is evolving rapidly
- Bash tool calls should always trigger PreToolUse hooks

**No events in AgentChute?**
- Ensure `codex_hooks = true` is present under `[features]` in `~/.codex/config.toml`
- Start a fresh Codex session after running `agentlint setup codex`
- Launch Codex from the same terminal where `AGENTCHUTE_API_URL`, `AGENTCHUTE_LICENSE_KEY`, and `AGENTCHUTE_ENABLED` are exported
- Run `agentlint agentchute status` and `agentlint sync` from the project root

**Need full file-write coverage?**
- Consider using AgentLint's MCP server alongside hooks for pre-validation
- Run `agentlint doctor` for alternative integration suggestions
