# Setup Guide: Grok CLI (xAI)

AgentLint supports Grok CLI via native hooks in `~/.grok/user-settings.json`.

## Installation

```bash
agentlint setup grok
```

This creates `.grok/settings.json` in your project root with hooks for:

- `PreToolUse` — blocks secrets, destructive commands, etc.
- `PostToolUse` — checks file quality after edits
- `UserPromptSubmit` — prompt-level rule evaluation
- `SubagentStart` — safety briefing injection
- `SubagentStop` — subagent transcript audit
- `Notification` — notification-triggered rules
- `Stop` — session summary report

## Hook Format

Grok uses a JSON-based hook protocol compatible with Claude Code's format:

- **Exit 0** — success; JSON output parsed
- **Exit 2** — block the action (deny permission)

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
agentlint setup grok --global
```

Installs to `~/.grok/user-settings.json` (affects all projects).

## Uninstall

```bash
agentlint uninstall grok
```

Removes only AgentLint hooks; preserves any other custom hooks you have configured.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `GROK_PROJECT_DIR` | Project directory override |
| `GROK_SESSION_ID` | Session ID for state tracking |
| `AGENTLINT_PROJECT_DIR` | Generic project directory (takes precedence) |
| `AGENTLINT_SESSION_ID` | Generic session ID (takes precedence) |

## Troubleshooting

**Hooks not firing?**
- Verify `.grok/settings.json` exists and contains a `"hooks"` key
- Check that the `agentlint` binary is on PATH or that `agentlint setup` embedded an absolute path
- Run `agentlint doctor` to diagnose installation issues
