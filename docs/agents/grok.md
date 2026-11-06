---
description: Install AgentLint's Grok CLI hooks and verify that matching tool calls reach the local engine.
---

# Grok CLI

[Host activity status](../diagnostics.md#host-activity-and-pending-approvals) records tool results. Untyped notifications cannot prove a native approval wait, so absent state remains unknown. Activity context uses Grok's top-level `additionalContext` field.

AgentLint runs as Grok CLI command hooks, in the same format as Claude Code, that call `agentlint check --adapter grok`.

Matching pre-tool hooks can deny an action on ERROR findings; post-tool hooks report what has already happened. Verify observation after setup and check the matchers below for the reported tool names. See [Coverage and limits](../coverage.md) and the [quickstart](../quickstart.md).

## Install

```bash
agentlint setup grok            # project: .grok/settings.json
agentlint setup grok --global   # user:    ~/.grok/user-settings.json
```

Note the different file names: project scope writes `settings.json`, user scope writes `user-settings.json`. Setup merges AgentLint entries into the `hooks` key, keeps your other settings, and uses the absolute path of the `agentlint` binary. If the project has no `agentlint.yml`, it creates one. `--dry-run` prints the result without writing.

## Verify

```bash
agentlint status
```

The `grok` line reports configured -> enabled -> observed. Make one tool call in Grok, then run `agentlint status` again.

## What is checked

| Event | Matcher | Command |
|-------|---------|---------|
| `PreToolUse` | `bash\|write\|edit` | `agentlint check --event PreToolUse --adapter grok` |
| `PostToolUse` | `bash\|write\|edit` | `agentlint check --event PostToolUse --adapter grok` |
| `UserPromptSubmit` | all | `agentlint check --event UserPromptSubmit --adapter grok` |
| `SubagentStart` | all | `agentlint check --event SubagentStart --adapter grok` |
| `SubagentStop` | all | `agentlint check --event SubagentStop --adapter grok` |
| `Notification` | all | `agentlint check --event Notification --adapter grok` |
| `SessionStart` | all | `agentlint check --event SessionStart --adapter grok` |
| `PostToolUse` / `PostToolUseFailure` (passive) | all | `agentlint observe --event <event> --adapter grok` |
| `Stop` | all | `agentlint report --adapter grok` |

Output follows the Claude Code format: a PreToolUse block is exit 0 with `hookSpecificOutput.permissionDecision: "deny"`; PostToolUse findings arrive as `additionalContext` (plus `"decision": "block"` for warnings and errors, and exit 2 for errors); other events with an ERROR exit 2 with a `systemMessage`. See [Claude Code](claude.md#what-is-checked).

## Configuration notes

- Grok tool names are lowercase (`bash`, `write`, `edit`); the matchers above use them.
- Grok's lowercase tool names are translated to the canonical `Bash`/`Write`/`Edit` before rules run, so every built-in shell and file rule applies.
- Project directory: `--project-dir`, then `AGENTLINT_PROJECT_DIR`, then `CLAUDE_PROJECT_DIR`, then the hook's working directory.
- Session state key: `AGENTLINT_SESSION_ID`, otherwise the parent process ID.

## Uninstall

```bash
agentlint uninstall grok            # project scope
agentlint uninstall grok --global   # user scope
```

Only AgentLint entries are removed.

## Troubleshooting

- **Hooks not firing:** confirm the file for your scope (`.grok/settings.json` or `~/.grok/user-settings.json`) has a `hooks` key with `agentlint` commands. `agentlint doctor` reports stale binary paths.
- General issues: [Diagnostics](../diagnostics.md). Cloud upload and policy: [AgentChute](../agentchute.md).
