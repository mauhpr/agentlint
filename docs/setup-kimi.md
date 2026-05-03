# Setup Guide: Kimi Code CLI (Moonshot AI)

AgentLint supports Kimi Code CLI via native hooks in `~/.kimi/config.toml`.

## Installation

```bash
agentlint setup kimi
```

This creates `.kimi/config.toml` in your project root with hooks for:

- `PreToolUse` — blocks secrets, destructive commands, etc.
- `PostToolUse` — checks file quality after edits
- `UserPromptSubmit` — prompt-level rule evaluation
- `SubagentStart` — safety briefing injection
- `SubagentStop` — subagent transcript audit
- `Notification` — notification-triggered rules
- `Stop` — session summary report

## Hook Format

Kimi uses a TOML-based hook configuration with `[[hooks]]` arrays. The hook protocol expects JSON on stdout:

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

## Global Installation

```bash
agentlint setup kimi --global
```

Installs to `~/.kimi/config.toml` (affects all projects).

## Uninstall

```bash
agentlint uninstall kimi
```

Removes only AgentLint hooks; preserves any other custom hooks you have configured.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `KIMI_PROJECT_DIR` | Project directory override |
| `KIMI_SESSION_ID` | Session ID for state tracking |
| `AGENTLINT_PROJECT_DIR` | Generic project directory (takes precedence) |
| `AGENTLINT_SESSION_ID` | Generic session ID (takes precedence) |

## Troubleshooting

**TOML parsing issues?**
- Kimi config uses standard TOML syntax. AgentLint requires Python 3.11+ (`tomllib`) or the `tomli` package for older Python versions
- If `tomllib`/`tomli` is unavailable, AgentLint falls back to a minimal parser that handles `[[hooks]]` arrays
- The fallback parser may not preserve complex TOML features (inline tables, multi-line strings). Install `tomli` for full compatibility

**Hooks not firing?**
- Verify `.kimi/config.toml` exists and contains `[[hooks]]` entries
- Run `agentlint doctor` to diagnose installation issues
