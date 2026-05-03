# Setup Guide: Cursor IDE

AgentLint supports Cursor IDE (v1.7+) via native hooks.

## Installation

```bash
agentlint setup cursor
```

This creates `.cursor/hooks.json` in your project root with hooks for:
- `preToolUse` — blocks secrets, destructive commands, etc.
- `postToolUse` — checks file quality after edits
- `beforeShellExecution` — audits shell commands
- `afterFileEdit` — formatting and quality feedback
- `beforeSubmitPrompt` — prompt validation
- `subagentStart` / `subagentStop` — subagent safety
- `stop` — session summary report

## Hook Format

Cursor hooks use a JSON-based protocol:

- **Exit 0** — success, JSON output parsed
- **Exit 2** — block the action (deny permission)
- **Other** — hook failure, action continues

Blocking output:
```json
{"permission": "deny", "agent_message": "[no-secrets] Secret detected"}
```

Advisory output:
```json
{"additional_context": "[max-file-size] File exceeds limit"}
```

## Global Installation

```bash
agentlint setup cursor --global
```

Installs to `~/.cursor/hooks.json` (affects all projects).

## Uninstall

```bash
agentlint uninstall cursor
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `CURSOR_PROJECT_DIR` | Project directory override |
| `CURSOR_SESSION_ID` | Session ID for state tracking |
| `AGENTLINT_PROJECT_DIR` | Generic project directory (takes precedence) |
| `AGENTLINT_SESSION_ID` | Generic session ID (takes precedence) |
