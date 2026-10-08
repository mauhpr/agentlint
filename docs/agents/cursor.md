# Cursor

AgentLint runs as Cursor hooks (`hooks.json`) that call `agentlint check --adapter cursor` on tool calls, shell commands, file edits, prompts and subagents.

## Install

```bash
agentlint setup cursor            # project: .cursor/hooks.json
agentlint setup cursor --global   # user:    ~/.cursor/hooks.json
```

Setup merges AgentLint entries into `hooks.json` (format `version: 1`), keeps your other hooks, and uses the absolute path of the `agentlint` binary. If the project has no `agentlint.yml`, it creates one. `--dry-run` prints the result without writing.

Reload the Cursor window so it picks up the new hooks.

## Verify

```bash
agentlint status
```

The `cursor` line reports configured -> enabled -> observed. Make one agent tool call in Cursor (for example, run a shell command), then run `agentlint status` again; "observed" comes from a heartbeat written on every hook call.

## What is checked

| Event | Matcher | Command |
|-------|---------|---------|
| `preToolUse` | `Shell\|Write\|Delete` | `agentlint check --event preToolUse --adapter cursor` |
| `postToolUse` | `Shell\|Write\|Delete` | `agentlint check --event postToolUse --adapter cursor` |
| `beforeShellExecution` | all | `agentlint check --event beforeShellExecution --adapter cursor` |
| `afterFileEdit` | all | `agentlint check --event afterFileEdit --adapter cursor` |
| `beforeSubmitPrompt` | all | `agentlint check --event beforeSubmitPrompt --adapter cursor` |
| `subagentStart` | all | `agentlint check --event subagentStart --adapter cursor` |
| `subagentStop` | all | `agentlint check --event subagentStop --adapter cursor` |
| `stop` | all | `agentlint report --adapter cursor` |

How results reach Cursor:

- **Any ERROR finding:** the hook exits 2, which blocks the action.
- **Pre-execution events with an ERROR** (`preToolUse`, `beforeShellExecution`): stdout also carries a deny decision:

  ```json
  {"permission": "deny", "user_message": "AgentLint blocked this action.", "agent_message": "[no-destructive-commands] ..."}
  ```

- **Everything else** (post-edit feedback, warnings, subagent briefings): `{"additional_context": "..."}`.

## Configuration notes

- Project directory: `--project-dir`, then `AGENTLINT_PROJECT_DIR`, then `CLAUDE_PROJECT_DIR`, then the hook's working directory.
- Session state key: `AGENTLINT_SESSION_ID`, then `CURSOR_SESSION_ID`, then the parent process ID.
- Cursor's native tool names (`Shell`, `Write`, `Delete`) are translated to the canonical `Bash`/`Write` before rules run, so shell and file rules apply to them.
- If you use the [AgentChute](../agentchute.md) cloud, Cursor must be launched from an environment that has its variables, because hooks inherit Cursor's environment.

## Uninstall

```bash
agentlint uninstall cursor            # project scope
agentlint uninstall cursor --global   # user scope
```

Only AgentLint entries are removed.

## Troubleshooting

- **Hooks not firing:** confirm `.cursor/hooks.json` exists in the opened workspace and reload the window. `agentlint doctor` reports missing or stale installs.
- General issues: [Diagnostics](../diagnostics.md). Cloud upload and policy: [AgentChute](../agentchute.md).
