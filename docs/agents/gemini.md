# Gemini CLI

AgentLint runs as Gemini CLI command hooks in `settings.json` that call `agentlint check --adapter gemini`.

## Install

```bash
agentlint setup gemini            # project: .gemini/settings.json
agentlint setup gemini --global   # user:    ~/.gemini/settings.json
```

Setup merges AgentLint entries into the `hooks` key, keeps your other hooks and settings, and uses the absolute path of the `agentlint` binary. If the project has no `agentlint.yml`, it creates one. `--dry-run` prints the result without writing.

Start a new Gemini CLI session after installing.

## Verify

```bash
agentlint status
```

The `gemini` line reports configured -> enabled -> observed. Make one tool call in Gemini CLI (for example, ask it to run `ls`), then run `agentlint status` again.

## What is checked

| Event | Matcher | Hook name | Command |
|-------|---------|-----------|---------|
| `BeforeTool` | `write_file\|replace\|run_shell_command\|bash` | `agentlint-pre` | `agentlint check --event BeforeTool --adapter gemini` |
| `AfterTool` | `write_file\|replace\|run_shell_command\|bash` | `agentlint-post` | `agentlint check --event AfterTool --adapter gemini` |
| `BeforeAgent` | all | `agentlint-prompt` | `agentlint check --event BeforeAgent --adapter gemini` |
| `AfterAgent` | `*` | `agentlint-stop` | `agentlint check --event AfterAgent --adapter gemini` |
| `SessionStart` | all | `agentlint-start` | `agentlint check --event SessionStart --adapter gemini` |
| `PreCompress` | all | `agentlint-compact` | `agentlint check --event PreCompress --adapter gemini` |

AgentLint maps these to its own events: `BeforeTool` is a pre-tool check, `AfterTool` a post-tool check, `BeforeAgent` a prompt check, `AfterAgent` the end-of-turn (Stop) check, and `PreCompress` a pre-compaction check.

How results reach Gemini CLI:

- **Any ERROR finding:** the hook exits 2.
- **`BeforeTool` with an ERROR:** stdout also carries a deny decision:

  ```json
  {"decision": "deny", "reason": "[no-secrets] ...", "systemMessage": "AgentLint blocked this action."}
  ```

- **Other findings:** `{"hookSpecificOutput": {"hookEventName": "...", "additionalContext": "..."}}`.

## Configuration notes

- Project directory: `--project-dir`, then `AGENTLINT_PROJECT_DIR`, then `CLAUDE_PROJECT_DIR`, then the hook's working directory.
- Session state key: `AGENTLINT_SESSION_ID`, otherwise the parent process ID.
- Gemini's native tool names (`run_shell_command`, `write_file`, `replace`) are translated to the canonical `Bash`/`Write`/`Edit` before rules run, so every built-in shell and file rule applies. Installations made before 2.9.0 don't match `run_shell_command`; re-run `agentlint setup gemini`.

## Uninstall

```bash
agentlint uninstall gemini            # project scope
agentlint uninstall gemini --global   # user scope
```

Only AgentLint entries are removed.

## Troubleshooting

- **Hooks not firing:** confirm `.gemini/settings.json` has a `hooks` key with `agentlint` commands and start a new session. Gemini uses `BeforeTool`/`AfterTool`, not `PreToolUse`/`PostToolUse`.
- General issues: [Diagnostics](../diagnostics.md). Cloud upload and policy: [AgentChute](../agentchute.md).
