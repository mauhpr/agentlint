# Continue

AgentLint runs as Continue command hooks in `.continue/settings.json`, using the same hook protocol as Claude Code.

## Install

```bash
agentlint setup continue            # project: .continue/settings.json
agentlint setup continue --global   # user:    ~/.continue/settings.json
```

Setup merges AgentLint entries into the `hooks` key, keeps your other hooks, and uses the absolute path of the `agentlint` binary. If the project has no `agentlint.yml`, it creates one. `--dry-run` prints the result without writing.

## Verify

```bash
agentlint status
```

The `continue` line reports configured -> enabled -> observed. Make one tool call in Continue, then run `agentlint status` again.

## What is checked

| Event | Matcher | Command |
|-------|---------|---------|
| `PreToolUse` | `Bash\|Edit\|Write` | `agentlint check --event PreToolUse --adapter continue` |
| `PostToolUse` | `Bash\|Edit\|Write` | `agentlint check --event PostToolUse --adapter continue` |
| `UserPromptSubmit` | all | `agentlint check --event UserPromptSubmit --adapter continue` |
| `SubagentStart` | all | `agentlint check --event SubagentStart --adapter continue` |
| `SubagentStop` | all | `agentlint check --event SubagentStop --adapter continue` |
| `Notification` | all | `agentlint check --event Notification --adapter continue` |
| `Stop` | all | `agentlint report --adapter continue` |

Output is identical to [Claude Code](claude.md#what-is-checked): a PreToolUse block is exit 0 with `hookSpecificOutput.permissionDecision: "deny"`; PostToolUse findings arrive as `additionalContext` (plus `"decision": "block"` for warnings and errors, and exit 2 for errors); other events with an ERROR exit 2 with a `systemMessage`.

## Configuration notes

- Continue merges hooks from `.continue/settings.json` with `.claude/settings.json`. AgentLint hooks installed for Claude Code in the same project therefore also apply in Continue; check both files if a hook runs unexpectedly.
- Project directory: `--project-dir`, then `AGENTLINT_PROJECT_DIR`, then `CLAUDE_PROJECT_DIR`, then the hook's working directory.
- Session state key: `AGENTLINT_SESSION_ID`, otherwise the parent process ID.

## Uninstall

```bash
agentlint uninstall continue            # project scope
agentlint uninstall continue --global   # user scope
```

Only AgentLint entries are removed.

## Troubleshooting

- **Hooks not firing:** confirm `.continue/settings.json` has a `hooks` key with `agentlint` commands. Check whether `.claude/settings.json` also has AgentLint hooks.
- General issues: [Diagnostics](../diagnostics.md). Cloud upload and policy: [AgentChute](../agentchute.md).
