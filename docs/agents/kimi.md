# Kimi Code CLI

AgentLint runs as Kimi Code CLI hooks, written as `[[hooks]]` entries in Kimi's TOML config, that call `agentlint check --adapter kimi`.

## Install

```bash
agentlint setup kimi            # project: .kimi/config.toml
agentlint setup kimi --global   # user:    ~/.kimi/config.toml
```

Setup adds one `[[hooks]]` table per event, replaces any earlier AgentLint entries, and uses the absolute path of the `agentlint` binary. If the project has no `agentlint.yml`, it creates one. `--dry-run` prints the entries without writing.

## Verify

```bash
agentlint status
```

The `kimi` line reports configured -> enabled -> observed. Make one tool call in Kimi, then run `agentlint status` again.

## What is checked

| Event | Matcher | Command |
|-------|---------|---------|
| `PreToolUse` | `Shell\|WriteFile\|StrReplaceFile` | `agentlint check --event PreToolUse --adapter kimi` |
| `PostToolUse` | `Shell\|WriteFile\|StrReplaceFile` | `agentlint check --event PostToolUse --adapter kimi` |
| `UserPromptSubmit` | all | `agentlint check --event UserPromptSubmit --adapter kimi` |
| `SubagentStart` | all | `agentlint check --event SubagentStart --adapter kimi` |
| `SubagentStop` | all | `agentlint check --event SubagentStop --adapter kimi` |
| `Notification` | all | `agentlint check --event Notification --adapter kimi` |
| `Stop` | all | `agentlint report --adapter kimi` |

Kimi uses the Claude Code output format: a PreToolUse block is exit 0 with `hookSpecificOutput.permissionDecision: "deny"`; PostToolUse findings arrive as `additionalContext` (plus `"decision": "block"` for warnings and errors, and exit 2 for errors); other events with an ERROR exit 2 with a `systemMessage`. See [Claude Code](claude.md#what-is-checked).

## Configuration notes

- Kimi's native tool names (`Shell`, `WriteFile`, `StrReplaceFile`) are translated to the canonical `Bash`/`Write`/`Edit` before rules run, so every built-in shell and file rule applies.
- AgentLint rewrites the whole TOML file when it installs or uninstalls. It keeps top-level scalar keys, one level of tables with simple values, and `[[hooks]]` entries. Comments, nested tables, arrays and inline tables are not preserved. If your `config.toml` uses them, run `agentlint setup kimi --dry-run` and add the printed entries by hand instead.
- Project directory: `--project-dir`, then `AGENTLINT_PROJECT_DIR`, then `CLAUDE_PROJECT_DIR`, then the hook's working directory.
- Session state key: `AGENTLINT_SESSION_ID`, otherwise the parent process ID.

## Uninstall

```bash
agentlint uninstall kimi            # project scope
agentlint uninstall kimi --global   # user scope
```

Only AgentLint `[[hooks]]` entries are removed. If the file cannot be parsed, uninstall leaves it untouched.

## Troubleshooting

- **Hooks not firing:** confirm `.kimi/config.toml` (or `~/.kimi/config.toml`) has `[[hooks]]` entries with `agentlint` commands.
- General issues: [Diagnostics](../diagnostics.md). Cloud upload and policy: [AgentChute](../agentchute.md).
