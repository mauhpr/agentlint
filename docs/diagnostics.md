# Hook and policy diagnostics

`agentlint policy status` shows the cached policy version, active cached rule IDs,
whether those rules are enforced, credential presence, and whether AgentChute
connectivity has been checked. Add `--online` to make a read-only connection
probe. A missing key stops refresh and event delivery but does not silently
disable valid cached rules. Cache changes apply on the next hook invocation;
restart the coding agent after changing environment variables it inherited.

To reproduce a hook result and save a minimized diagnostic bundle, pipe the
original hook input to `agentlint check` with `--diagnostic-bundle`:

```sh
agentlint check --event PostToolUse --adapter codex \
  --diagnostic-bundle /tmp/agentlint-diagnostic.json < hook-input.json
```

The bundle contains adapter and AgentLint versions, event and tool type, input
field names, a redacted command operation and input hash, evaluated and fired rule IDs, and
the Codex output validation result. It omits raw command arguments, prompts,
file contents, paths, rule messages and credentials. Review the file before
sharing it. Diagnostic files are written with owner-only permissions.

New session recordings and AgentChute event summaries likewise omit raw Bash
arguments, prompt text, file paths, search queries, URLs and task descriptions.
Existing recordings made by older versions are **not** rewritten. Review or
delete old files with `agentlint recordings list` and `agentlint recordings clear`.

Read-only cloud detection accepts only simple allowlisted `gcloud` and `aws`
inspection forms, including literal `env NAME=value` wrappers. PostgreSQL
inspection through `psql -c` or a repository-local `psql -f` file is exempted
from production targeting only when the script explicitly starts with
`BEGIN READ ONLY`, contains only SELECT/SHOW/EXPLAIN SELECT statements, and
ends with COMMIT or ROLLBACK. Unknown syntax remains checked.

## Coverage: configured, enabled, observed

`agentlint status` reports each coding agent at three levels:

- **configured** — an AgentLint hook exists at project scope (`.codex/hooks.json`)
  or user scope (`~/.codex/hooks.json`). Project scope wins. Hook files are parsed
  to list the wired events. A hook that calls a script which delegates to
  AgentLint (for example a workspace routing wrapper) is reported as `wrapper`,
  not `missing`.
- **enabled** — where it can be read locally, e.g. Codex `[features].hooks` in
  `~/.codex/config.toml`. Codex hook *trust* is confirmed in Codex's `/hooks`
  review; AgentLint cannot read it.
- **observed** — every `agentlint check` invocation records a heartbeat in
  `~/.cache/agentlint/heartbeat/<platform>.json` (event, tool type, a project
  fingerprint, version, timestamp; no commands, paths or content). Override the
  directory with `AGENTLINT_HEARTBEAT_DIR`. "never observed" after a tool call
  means the hook is not reaching AgentLint (untrusted, not reloaded, or a
  matcher mismatch).

`doctor --fix` never installs project hooks when a user-scope installation or
wrapper already covers the platform. `status --json` emits the same data,
including the effective policy layers (workspace, repository), the file that
configured each rule, required rules and exception count.

## Degraded cloud operation

`status` and `doctor` show the AgentChute delivery state as `healthy`, `off` or
`degraded`, with pending count, the age of the oldest undelivered event,
consecutive failures, the next retry time, and the last HTTP status. HTTP 429
and 503 responses honour `Retry-After` (seconds or HTTP date, at most one hour).
More than 10,000 undelivered events or a 50 MB queue file produce a warning;
events are never discarded automatically (`agentlint queue discard-pending`
remains an explicit action).

Both commands list what is **still enforced locally**: pack rules, required
workspace rules and the cached organization policy (or an explicit statement
that no organization rules are cached). `doctor` is read-only by default; it
refreshes the cloud policy only with `--online` or `--fix`.

## Patch previews

Codex `apply_patch` denials name the file, hunk number, the first context line
(credential-like values masked) and, for ambiguous hunks, every matching line
number. Preview a patch with the identical validator and rules, without writing
files or touching session, heartbeat, recording or queue state:

```sh
agentlint check-patch change.patch --project-dir . [--cwd subdir] [--json]
```

It exits 1 when the patch would be denied. The MCP server exposes the same
check as `check_patch`.
