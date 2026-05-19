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

For AgentChute local testing, set the API URL before launching Cursor:

```bash
export AGENTCHUTE_API_URL=http://localhost:8000/v1
export AGENTCHUTE_LICENSE_KEY=ac_team_...
export AGENTCHUTE_ENABLED=true
```

Reload the Cursor window after running `agentlint setup cursor` so it loads the
updated hook config.

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

## Troubleshooting

**No events in AgentChute?**
- Verify `.cursor/hooks.json` exists in the project
- Reload the Cursor window after installing hooks
- Ensure Cursor inherits `AGENTCHUTE_API_URL`, `AGENTCHUTE_LICENSE_KEY`, and `AGENTCHUTE_ENABLED`
- Run `agentlint agentchute status` from the project root
- If events are queued, run `agentlint agentchute flush` as a support/debug step
