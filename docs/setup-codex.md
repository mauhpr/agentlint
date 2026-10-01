# Setup Guide: Codex CLI (OpenAI)

AgentLint supports Codex CLI via native hooks in `~/.codex/hooks.json`.

## Installation

```bash
agentlint setup codex
```

This creates `.codex/hooks.json` in your project root with hooks for:

- `PreToolUse` — checks Bash commands and every file in native `apply_patch` edits
- `PostToolUse` — checks Bash commands and actual file contents after a patch
- `UserPromptSubmit` — prompt-level rule evaluation
- `SessionStart` — session initialization
- `Stop` — session summary report

Codex also requires native hooks to be enabled globally. `agentlint setup codex`
updates `~/.codex/config.toml` for you by adding the flag under `[features]`:

```toml
[features]
hooks = true
```

Do not append `hooks = true` to the end of `config.toml` manually. TOML
assigns bare keys to the most recent table, so appending after a section such as
`[tui.model_availability_nux]` can make Codex fail to load its config.
AgentLint also removes legacy or misplaced `codex_hooks` keys when it repairs
Codex setup.

Restart Codex from the terminal where your AgentLint/AgentChute environment
variables are set:

```bash
codex
```

For AgentChute local testing, set the API URL before starting Codex:

```bash
export AGENTCHUTE_API_URL=http://localhost:8000/v1
export AGENTCHUTE_LICENSE_KEY=ac_team_...
export AGENTCHUTE_ENABLED=true
```

## Important: Codex Hook Coverage

AgentLint 2.6.0 installs `^(Bash|apply_patch)$` tool matchers. Current Codex supports
these native events, including calls made through code mode. Older Codex versions
may have narrower coverage; verify hook discovery and trust in your installation.

Patch input uses `tool_input.command`. AgentLint translates additions, updates,
deletions and renames into per-file rule contexts. It checks both paths of a rename
and aggregates findings across all files. Before execution it reads existing files
and applies hunks in memory; it never writes the patch itself. Post-tool checks read
the actual resulting files and compare them with cached pre-edit content.

Inspection rejects out-of-project paths (including symlink escapes), missing or
ambiguous hunks, unsupported envelopes, overwrites by Add/Move operations, patches
over 2 MB, files over 5 MB and batches over 200 targets. Relative paths use the native
tool working directory, bounded by `--project-dir`. These checks are deliberately
conservative; a rejected patch can be split or made unambiguous, but must not be
rerouted through a shell write to bypass the check.

File checks such as secrets, CI pipeline edits and test weakening now receive the
structured input they expect. Their configured severities and reviewed exemptions
still apply. Arbitrary MCP actions need tool-specific semantics and are not covered
by this adapter. Hooks are not a security sandbox.

After updating an existing installation, rerun setup in its intended scope and
review/trust changed hook definitions using Codex `/hooks`. Custom scoped wrappers
must update their matchers and project/session routing deliberately. Do not write
trust hashes or use hook-trust bypass flags as part of setup.

Official hook behavior: https://learn.chatgpt.com/docs/hooks

## Hook Format

Codex uses a JSON-based hook protocol:

- **Exit 0** — success; JSON output parsed
- **Exit 2** — block the action

Blocking output:
```json
{
  "hookSpecificOutput": {
    "permissionDecision": "deny",
    "permissionDecisionReason": "[no-secrets] Possible secret token detected"
  }
}
```

Codex also supports a legacy `decision: "block"` format; AgentLint uses the modern `permissionDecision` protocol by default.

## Global Installation

```bash
agentlint setup codex --global
```

Installs to `~/.codex/hooks.json` (affects all projects).

## Uninstall

```bash
agentlint uninstall codex
```

Removes only AgentLint hooks; preserves any other custom hooks you have configured.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `CODEX_PROJECT_DIR` | Project directory override |
| `CODEX_SESSION_ID` | Session ID for state tracking |
| `AGENTLINT_PROJECT_DIR` | Generic project directory (takes precedence) |
| `AGENTLINT_SESSION_ID` | Generic session ID (takes precedence) |
| `AGENTLINT_WORKSPACE_CONFIG` | Explicit workspace defaults and required rules; see [configuration](configuration.md#workspace-policy-v260) |

## Troubleshooting

**Hooks not firing for Write/Edit?**
- Confirm AgentLint is at least 2.6.0 and the matcher includes `apply_patch`.
- Review/trust the new definition in Codex `/hooks` and restart if needed.
- Codex reports `apply_patch`, not Claude's `Write`/`Edit`, in native payloads.

**No events in AgentChute?**
- Ensure `hooks = true` is present under `[features]` in `~/.codex/config.toml`
- Start a fresh Codex session after running `agentlint setup codex`
- Launch Codex from the same terminal where `AGENTCHUTE_API_URL`, `AGENTCHUTE_LICENSE_KEY`, and `AGENTCHUTE_ENABLED` are exported
- Run `agentlint agentchute status` from the project root
- If events are queued, run `agentlint agentchute flush` as a support/debug step

**Need coverage for other tools?**
- Configure an integration that understands that tool's arguments and side effects.
- Run repository CI checks too; a shell-pattern guard cannot inspect every script
  body, remote operation or opaque MCP call.
