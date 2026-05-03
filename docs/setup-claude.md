# Setup Guide: Claude Code

AgentLint supports Claude Code via native hooks in `.claude/settings.json`.

## Installation

```bash
agentlint setup claude
```

This creates `.claude/settings.json` in your project root with hooks for:

- `PreToolUse` — blocks secrets, destructive commands, force-pushes, etc.
- `PostToolUse` — checks file quality after edits
- `UserPromptSubmit` — prompt-level rule evaluation
- `SubagentStart` — safety briefing injection
- `SubagentStop` — subagent transcript audit
- `Notification` — notification-triggered rules
- `Stop` — session summary report

## Hook Format

Claude Code uses a JSON-based hook protocol:

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

Advisory output (warnings):
```json
{
  "hookSpecificOutput": {
    "additionalContext": "[max-file-size] File exceeds limit"
  }
}
```

## Global Installation

```bash
agentlint setup claude --global
```

Installs to `~/.claude/settings.json` (affects all projects).

## Uninstall

```bash
agentlint uninstall claude
```

Removes only AgentLint hooks; preserves any other custom hooks you have configured.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `CLAUDE_PROJECT_DIR` | Project directory override |
| `CLAUDE_SESSION_ID` | Session ID for state tracking |
| `AGENTLINT_PROJECT_DIR` | Generic project directory (takes precedence) |
| `AGENTLINT_SESSION_ID` | Generic session ID (takes precedence) |

## Troubleshooting

**Hooks not firing?**
- Verify `.claude/settings.json` exists and contains a `"hooks"` key
- Check that the `agentlint` binary is on PATH or that `agentlint setup` embedded an absolute path
- Run `agentlint doctor` to diagnose installation issues

**Blocking rules not actually blocking?**
- Ensure the hook command returns exit code 0 with `permissionDecision: "deny"` in the JSON output
- AgentLint handles this automatically; if you see `{"systemMessage": "BLOCKED"}` with exit 2, the protocol is wrong
