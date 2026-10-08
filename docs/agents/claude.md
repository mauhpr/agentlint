# Claude Code

AgentLint runs as a set of Claude Code command hooks that call `agentlint check` on tool calls, prompts and subagent events.

## Install

```bash
agentlint setup claude            # project: .claude/settings.json
agentlint setup claude --global   # user:    ~/.claude/settings.json
```

Setup merges AgentLint entries into the `hooks` key of the settings file and leaves your other hooks alone. Each hook command uses the absolute path of the `agentlint` binary found at install time. If the project has no `agentlint.yml`, setup also creates one. Use `--dry-run` to print the result without writing.

Restart Claude Code in the project so it loads the new hooks.

## Verify

```bash
agentlint status
```

The `claude` line reports configured -> enabled -> observed. "Observed" comes from a heartbeat that `agentlint check` writes on every hook call, so make one tool call in Claude Code (for example, ask it to run `ls`), then run `agentlint status` again.

## What is checked

| Event | Matcher | Command |
|-------|---------|---------|
| `PreToolUse` | `Bash\|Edit\|Write` | `agentlint check --event PreToolUse` |
| `PostToolUse` | `Bash\|Edit\|Write` | `agentlint check --event PostToolUse` |
| `UserPromptSubmit` | all | `agentlint check --event UserPromptSubmit` |
| `SubagentStart` | all | `agentlint check --event SubagentStart` |
| `SubagentStop` | all | `agentlint check --event SubagentStop` |
| `Notification` | all | `agentlint check --event Notification` |
| `Stop` | all | `agentlint report` |

How results reach Claude Code:

- **PreToolUse, blocking (ERROR):** exit code 0 with a JSON deny decision. Claude Code does not run the tool and shows the reason to the model.

  ```json
  {
    "hookSpecificOutput": {
      "hookEventName": "PreToolUse",
      "permissionDecision": "deny",
      "permissionDecisionReason": "[no-secrets] Possible secret token detected (prefix 'sk_live_')\n  File: config.py\n  ..."
    }
  }
  ```

- **PreToolUse, advisory (WARNING/INFO):** exit 0 with `hookSpecificOutput.additionalContext`, which is added to the model's context.
- **PostToolUse:** `hookSpecificOutput.additionalContext` with the findings; warnings and errors also set `"decision": "block"` with a `reason` so the model acts on them. If any finding is an ERROR the process exits 2.
- **SubagentStart:** the safety briefing is injected into the subagent as `additionalContext`. See [Subagent safety](../subagent-safety.md).
- **Other events** (`UserPromptSubmit`, `SubagentStop`, `Notification`): a `systemMessage` for the user; exit 2 if any finding is an ERROR.
- **Stop:** `agentlint report` prints the session summary.

## Configuration notes

- Project directory: `--project-dir`, then `AGENTLINT_PROJECT_DIR`, then `CLAUDE_PROJECT_DIR` (set by Claude Code), then the current directory.
- Session state key: `AGENTLINT_SESSION_ID`, then `CLAUDE_SESSION_ID`, then the parent process ID.
- The installed hooks do not pass `--adapter`; with no other agent's environment variables present, `agentlint check` uses the Claude adapter.
- Whether a subagent's tool calls trigger the session's hooks depends on your Claude Code version; see [Subagent safety](../subagent-safety.md) for what AgentLint does about it.

## Uninstall

```bash
agentlint uninstall claude            # project scope
agentlint uninstall claude --global   # user scope
```

Only AgentLint entries are removed. If nothing else remains, the settings file is deleted.

## Troubleshooting

- **Hooks not firing:** confirm `.claude/settings.json` (or `~/.claude/settings.json`) has a `hooks` key with `agentlint` commands, that the binary path in those commands still exists, and that you restarted Claude Code. `agentlint doctor` reports a stale binary path; `agentlint doctor --fix` reinstalls it.
- **Blocking rule did not block:** the PreToolUse deny must be exit 0 plus JSON. Capture what AgentLint saw with `agentlint check --event PreToolUse --diagnostic-bundle /tmp/al.json < payload.json`.
- General issues: [Diagnostics](../diagnostics.md). Cloud upload and policy: [AgentChute](../agentchute.md).
