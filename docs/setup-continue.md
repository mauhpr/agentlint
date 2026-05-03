# Setup Guide: Continue.dev

AgentLint supports Continue.dev via native hooks in `.continue/settings.json`.

## Installation

```bash
agentlint setup continue
```

This creates `.continue/settings.json` in your project root with hooks for:

- `PreToolUse` — blocks secrets, destructive commands, etc.
- `PostToolUse` — checks file quality after edits
- `UserPromptSubmit` — prompt-level rule evaluation
- `SubagentStart` — safety briefing injection
- `SubagentStop` — subagent transcript audit
- `Notification` — notification-triggered rules
- `Stop` — session summary report

## Hook Format

Continue.dev uses a Claude Code-compatible JSON hook protocol:

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

Continue.dev merges settings from `.continue/settings.json` with `.claude/settings.json` natively, so you can use both Claude Code and Continue.dev with the same AgentLint installation.

## Global Installation

```bash
agentlint setup continue --global
```

Installs to `~/.continue/settings.json` (affects all projects).

## Uninstall

```bash
agentlint uninstall continue
```

Removes only AgentLint hooks; preserves any other custom hooks you have configured.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `CONTINUE_PROJECT_DIR` | Project directory override |
| `CONTINUE_SESSION_ID` | Session ID for state tracking |
| `AGENTLINT_PROJECT_DIR` | Generic project directory (takes precedence) |
| `AGENTLINT_SESSION_ID` | Generic session ID (takes precedence) |

## Troubleshooting

**Hooks not firing?**
- Verify `.continue/settings.json` exists and contains a `"hooks"` key
- Continue.dev also reads `.claude/settings.json`; ensure AgentLint hooks are in the expected location
- Run `agentlint doctor` to diagnose installation issues
