# MCP server

`agentlint-mcp` exposes the AgentLint rule engine over the [Model Context Protocol](https://modelcontextprotocol.io) (stdio transport). An agent can check content, a patch or an event before acting, fix every finding in one pass, and avoid repeated hook blocks.

Install and host configuration (Claude Code, Claude Desktop, Cursor, Gemini CLI, Codex): [MCP hosts](agents/mcp-hosts.md).

## How it relates to hooks

- **Hooks** enforce. They run on every matching tool call whether or not the agent asks.
- **MCP** advises. The agent calls it when it chooses to.

Use both: MCP to pre-check, hooks as the safety net. MCP checks and hook checks run independently; a clean MCP result does not stop a hook from blocking if the content, tool or event differs.

## Project and session

- Config: `agentlint.yml` from `AGENTLINT_PROJECT_DIR`, then `CLAUDE_PROJECT_DIR`, then the server's working directory.
- Session key (`get_session`, `suppress_rule`, `agentlint://session`): `AGENTLINT_SESSION_ID`, then `MCP_SESSION_ID`, then the parent process ID.

## Tools

All tools return a JSON string.

### `check_content`

Check file content or a Bash command against the active rules.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `content` | string | required | File content, or the command when `tool_name` is `Bash` |
| `file_path` | string | required | Target path, used for rule matching and monorepo pack resolution. Use `""` for Bash. |
| `tool_name` | string | `"Write"` | `Write`, `Edit` or `Bash` |
| `event` | string | `"PreToolUse"` | `PreToolUse` / `PostToolUse`, or the normalized `pre_tool_use` / `post_tool_use` |

Returns an array of violations; `[]` means clean. An unknown `event` returns `[{"error": "..."}]`.

```json
[
  {
    "rule_id": "no-secrets",
    "message": "Possible secret token detected (prefix 'sk_live_')",
    "severity": "error",
    "file_path": "config.py",
    "line": null,
    "suggestion": "Use environment variables instead of hard-coded secrets.",
    "operation": "Write",
    "policy_source": "built-in universal pack; built-in defaults (no policy file)"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `rule_id` | string | Rule identifier |
| `message` | string | What was found |
| `severity` | string | `error` (would block), `warning` or `info` |
| `file_path` | string or null | File, if applicable |
| `line` | int or null | Line, if known |
| `suggestion` | string or null | How to fix it |
| `operation` | string | Present only when known |
| `policy_source` | string | Which config layer or pack produced the finding; present only when known |

With `projects:` in `agentlint.yml`, packs are resolved from `file_path`, so pass the path relative to the project root.

### `check_patch`

Preview a Codex `apply_patch` payload with the same validator and rules as the Codex hook. Read-only: nothing is written and the session is not touched. Equivalent to `agentlint check-patch`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `patch` | string | required | The full patch text (`*** Begin Patch` ... `*** End Patch`) |
| `cwd` | string or null | `null` | Working directory for relative patch paths, relative to the project directory |

Returns:

```json
{"decision": "deny", "violations": [ ... ]}
```

`decision` is `allow` or `deny`. An ambiguous or missing hunk produces a violation naming the file, hunk, repeated context and candidate line numbers. See [Codex](agents/codex.md#apply_patch-inspection) for the full rules.

### `check_event`

Check any event in AgentLint's normalized form, for frameworks whose tool input does not fit `check_content`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `event` | string | required | Normalized event name: `pre_tool_use`, `post_tool_use`, `user_prompt`, `stop`, and so on (see [Generic integration](agents/generic.md#input)). Hook names such as `PreToolUse` are rejected. |
| `tool_name` | string | required | Use `Bash`, `Write` or `Edit` for built-in rules to match |
| `tool_input` | object | required | For example `{"command": "..."}` or `{"file_path": "...", "content": "..."}` |
| `file_content` | string or null | `null` | Current file content, for rules that need it |

Returns an array of violations, same shape as `check_content`. It does not resolve per-project packs.

### `list_rules`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pack` | string or null | `null` | Only rules from this pack |

Returns every available rule, not only the active ones: all built-in packs, installed rule plugins, the project's `custom_rules_dir`, and cached [AgentChute](agentchute.md) policy rules. Sorted by pack, then id.

```json
[
  {
    "id": "no-secrets",
    "description": "Prevents writing secrets or credentials into source files",
    "severity": "error",
    "events": ["PreToolUse"],
    "pack": "universal"
  }
]
```

Use `get_config` to see which packs are active. See [Rules](rules.md) for the catalogue.

### `get_config`

No parameters. Returns the loaded configuration:

```json
{"severity": "standard", "packs": ["universal", "quality"], "custom_rules_dir": null, "rules": {}}
```

`packs` is the effective list; `universal` and `quality` are always included unless excluded. See [Configuration](configuration.md).

### `get_session`

No parameters. Returns the session state object for the current session key (suppressed rules, counters, cached file state and similar). `{}` if there is no session yet. The keys are internal and may change.

### `suppress_rule`

Suppress a rule for the rest of the session.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rule_id` | string | required | Rule to suppress |

Returns:

```json
{"suppressed": "drift-detector", "total_suppressed": 1}
```

ERROR-severity findings are never suppressed: the id is stored, but the engine ignores it for errors. Suppressions affect hooks only if the hooks use the same session key (set `AGENTLINT_SESSION_ID` for both).

## Resources

| URI | Content |
|-----|---------|
| `agentlint://rules` | Same as `list_rules()` with no filter |
| `agentlint://config` | Same as `get_config()` |
| `agentlint://session` | Same as `get_session()` |

## Recipes

**Pre-check a write.** Call `check_content(content=code, file_path="src/app.py")`, fix every finding, re-check, then write. The PreToolUse hook passes on the first try.

**Pre-check a command.** `check_content(content="docker rm -f $(docker ps -aq)", file_path="", tool_name="Bash")`.

**Preview a Codex patch.** `check_patch(patch=patch_text)`; on `deny`, fix the named hunk and retry.

**Quiet a noisy warning.** `suppress_rule(rule_id="drift-detector")` after acknowledging it.

## Troubleshooting

- **Server will not start:** install the extra with `pip install "agentlint[mcp]"`.
- **Unexpected rules:** check `get_config`. The server reads `agentlint.yml` from `AGENTLINT_PROJECT_DIR`; set it to an absolute path in the host config.
- **MCP says clean, hook blocks:** compare the `event`, `tool_name` and content with what the agent actually sent. Hooks also see session state that `check_content` does not.
- General issues: [Diagnostics](diagnostics.md).
