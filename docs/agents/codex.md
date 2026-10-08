# Codex CLI

AgentLint runs as Codex native command hooks that check `Bash` commands and every file touched by `apply_patch`.

## Install

```bash
agentlint setup codex            # project: .codex/hooks.json
agentlint setup codex --global   # user:    ~/.codex/hooks.json
```

Setup merges AgentLint entries into `hooks.json`, keeps your other hooks, and uses the absolute path of the `agentlint` binary. If the project has no `agentlint.yml`, it creates one. `--dry-run` prints the result without writing.

Codex also needs hooks enabled in `~/.codex/config.toml`. Setup adds this under the existing `[features]` table (or creates it) and removes legacy `codex_hooks` keys:

```toml
[features]
hooks = true
```

Do not append `hooks = true` to the end of the file by hand. TOML assigns a bare key to the most recent table, so it can land in an unrelated section and stop Codex from loading its config.

Restart Codex from a terminal that has any AgentLint or AgentChute environment variables you rely on.

## Verify

1. Start Codex and open `/hooks`. Review and trust the AgentLint hook definitions. Codex will not run new or changed hooks until you do, and AgentLint never writes trust state for you.
2. Make one tool call (for example, ask Codex to run `ls`).
3. Run:

   ```bash
   agentlint status
   ```

   The `codex` line reports configured -> enabled -> observed. "Enabled" reflects `[features].hooks` in `~/.codex/config.toml`. "Observed" comes from a heartbeat written on every hook call. If it stays "never observed" after a tool call, the hook is not reaching AgentLint: check `/hooks` trust and reload the session.

`status` and `doctor` recognize user-scope installs and hook commands that delegate to your own wrapper script. In those cases `doctor --fix` does not add a second project-level integration.

## What is checked

| Event | Matcher | Command |
|-------|---------|---------|
| `PreToolUse` | `^(Bash\|apply_patch)$` | `agentlint check --event PreToolUse --adapter codex` |
| `PostToolUse` | `^(Bash\|apply_patch)$` | `agentlint check --event PostToolUse --adapter codex` |
| `UserPromptSubmit` | all | `agentlint check --event UserPromptSubmit --adapter codex` |
| `SessionStart` | all | `agentlint check --event SessionStart --adapter codex` |
| `Stop` | all | `agentlint report --adapter codex` |

All hooks have a 30-second timeout. The Codex formatter always exits 0; decisions are carried in JSON:

- **PreToolUse, blocking:** `hookSpecificOutput.permissionDecision: "deny"` with `permissionDecisionReason`.
- **PreToolUse, advisory:** `hookSpecificOutput.additionalContext`.
- **PostToolUse:** `additionalContext` with all findings; ERRORs add `"decision": "block"` and a `reason`.
- **UserPromptSubmit:** `additionalContext`; ERRORs add `"decision": "block"`.
- **SessionStart:** `additionalContext`; ERRORs add `"continue": false`.

AgentLint validates its own Codex response before printing it. An invalid response, malformed hook input or a configuration error exits 2 with a message on stderr.

### apply_patch inspection

Codex sends patches in `tool_input.command`. AgentLint splits a patch into per-file checks for additions, updates, deletions and renames (both paths of a rename are checked) and reports findings across all files. Before execution it reads existing files and applies the hunks in memory; it never writes the patch. After execution, `PostToolUse` reads the real resulting files and compares them with the cached pre-edit content.

A patch is denied if it:

- touches a path outside the project, including through a symlink;
- has a missing or ambiguous hunk, or an unsupported envelope;
- overwrites an existing file with an Add or Move operation;
- exceeds 2 MB, targets a file over 5 MB, or touches more than 200 files.

Relative paths resolve against the tool's working directory, bounded by the project directory. A denied ambiguous hunk names the file, the hunk, the repeated context line and the candidate line numbers. Add more unique context lines; an `@@` anchor only skips matches before the anchor line. Do not reroute a rejected patch through a shell write.

Preview a patch with the same validator and rules, without writing anything:

```bash
agentlint check-patch change.patch --project-dir .
agentlint check-patch change.patch --json      # {decision, rules_evaluated, violations}
```

It exits 1 when the patch would be denied. MCP clients can use the `check_patch` tool instead (see [MCP](../mcp.md)).

## Configuration notes

- Project directory: `--project-dir`, then `AGENTLINT_PROJECT_DIR`, then `CODEX_PROJECT_DIR`, then the tool's working directory from the hook payload.
- Session state is keyed on the Codex `session_id` from the payload unless `AGENTLINT_SESSION_ID` is set.
- `AGENTLINT_WORKSPACE_CONFIG` points at shared workspace defaults and required rules; see [Configuration](../configuration.md).
- Only native `Bash` and `apply_patch` are interpreted. Arbitrary MCP tool calls have their own argument semantics and are not treated as shell or file operations. Hooks are not a security sandbox; keep running repository CI checks ([CI](../ci.md)).
- If you use a custom wrapper script, update its matchers and project/session routing yourself when AgentLint's hook definitions change, then re-trust it in `/hooks`. Do not write trust hashes or use hook-trust bypass flags.

Codex hook reference: https://developers.openai.com/codex/hooks

## Uninstall

```bash
agentlint uninstall codex            # project scope
agentlint uninstall codex --global   # user scope
```

Only AgentLint entries are removed. `[features].hooks` in `~/.codex/config.toml` is left as is.

## Troubleshooting

- **Never observed:** trust the hooks in `/hooks`, confirm `hooks = true` is under `[features]`, and start a fresh Codex session.
- **Edits not checked:** make sure the matcher includes `apply_patch`. Codex reports `apply_patch`, not `Write`/`Edit`. Rerun `agentlint setup codex` in the scope you use and re-trust.
- **Patch denied as ambiguous or missing:** follow the line numbers in the denial and preview with `agentlint check-patch`.
- General issues: [Diagnostics](../diagnostics.md). No events in the cloud dashboard: [AgentChute](../agentchute.md) and `agentlint agentchute status`.
