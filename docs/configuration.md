# Configuration

AgentLint reads `agentlint.yml` (or `agentlint.yaml`, `.agentlint.yml`) from the
project root. `agentlint init` writes one with detected defaults. Without a file,
AgentLint runs with built-in defaults.

```yaml
# agentlint.yml — a typical starting point
severity: standard          # strict | standard | relaxed
packs: [python, security]   # universal + quality are always added

rules:
  max-file-size:
    limit: 400
  no-destructive-commands:
    allow_operations:
      - { binary: rm, args_prefix: ["-rf", "build"] }
```

Every rule and its options are listed in [Rules](rules.md). Commands are in the
[CLI reference](cli.md).

## Packs

Rules are grouped into packs. `universal` and `quality` are always active.

| Key | Effect |
|-----|--------|
| `packs: [...]` | Packs to enable in addition to the core packs. Disables stack detection. |
| `stack: auto` | Default when `packs` is absent: enable packs detected from project files. |
| `exclude_packs: [...]` | Turn a pack off deliberately, including a core pack (`[quality]`). |
| `drift_ignore_packs: [...]` | Don't report the listed packs as [drift](#pack-drift). |

Stack detection enables `python` for `pyproject.toml`/`setup.py`, `frontend` for
`package.json`, `react` when React is a dependency, and `seo` for SSR/SSG
frameworks. An `AGENTS.md` can add packs too (see [AGENTS.md](#agentsmd-import)).
`security` and `autopilot` are always opt-in.

Custom packs work the same way: name the pack in `packs:` and point
`custom_rules_dir` at your rule files. See [Custom rules](custom-rules.md).
`agentlint doctor` reports custom rules whose pack isn't enabled.

### Pack drift

When `packs:` is explicit, `agentlint status` and `agentlint doctor` compare it
with the repository (a bounded scan that skips dependency folders, nested
repositories and worktrees) and report packs the code calls for but the
configuration omits — for example a "Python-only" config in a repository that
contains `ui/package.json` and React components. Nothing is changed for you.
Add the pack, enable it for that directory with [`projects`](#monorepos), or
list it under `drift_ignore_packs`. Workspace baselines are not checked for
drift.

## Severity

`severity` changes how findings are reported:

| Mode | Effect |
|------|--------|
| `standard` | As each rule defines (default). |
| `strict` | WARNING becomes ERROR, INFO becomes WARNING. |
| `relaxed` | WARNING becomes INFO. |

Only ERROR findings block. Warnings and info are returned to the agent as
advice, on every platform.

## Rules

Each key under `rules:` is a rule ID. `enabled: false` turns a rule off; other
keys are rule options (see [Rules](rules.md)).

```yaml
rules:
  no-todo-left:
    enabled: false
  max-file-size:
    limit: 300
  drift-detector:
    threshold: 5
```

Keys placed directly under `rules:` are defaults for every rule that reads them;
a per-rule value overrides the default (lists are replaced, not merged):

```yaml
rules:
  strict_mode: true
  allow_paths: ["*.log"]
  no-secrets:
    strict_mode: false
```

## Exempting files

```yaml
rules:
  ignore_paths:                # skip every rule for these files
    - "**/generated/**"
  max-file-size:
    allow_paths: ["**/legacy_*.py"]   # skip one rule for these files
  no-unnecessary-async:
    ignore_paths: ["app/api/*_routes.py"]
    reason: "FastAPI route consistency"
```

Patterns use `fnmatch` globs and match the full path, the project-relative path
or the file name.

Inside a file:

```python
# agentlint:ignore-file
# agentlint:ignore max-file-size reason="generated parser"
# agentlint:ignore-next-line
```

All three forms suppress warnings and errors (except [required
rules](#workspace-policy)). A `reason="..."` appears in the session summary
(`agentlint report --summary`).

`no-destructive-commands` and `no-bash-file-write` treat `/tmp/`,
`/var/folders/` and `/private/tmp/` as scratch space. Add prefixes with
`safe_path_prefixes` (values containing `$TMPDIR` are expanded).

## Shell commands

AgentLint splits shell commands joined by `&&`, `||`, `;`, `|`, `&` or newlines
into operations and classifies each one:

- **display** — `echo`, `printf`;
- **read-only** — `grep`, `rg`, `cat`, `ls`, `git status/log/diff/show`,
  `gh pr view/list`, `find` without actions, `sed` without `-i`, and a short list
  of cloud and `psql` read commands;
- **state-changing** — everything else.

Operation guards only look at state-changing operations, so
`grep "rm -rf" build.log` is not a destructive command, and
`git push -u origin feat && gh pr create --base main` is not a push to `main`.

Anything AgentLint can't model exactly — `$(...)` and backticks, subshells,
heredocs, unterminated quotes, or data piped into an interpreter (`| bash`,
`| xargs`, `| ssh`) — is checked against the original text, as before.
Credential, file-write, custom and organization rules always see the original
command.

### Allowing specific operations

Use `allow_operations` to allow one kind of operation for a rule. It applies to
the matching operation only; other operations in the same command are still
checked.

```yaml
rules:
  no-destructive-commands:
    allow_operations:
      - binary: rm
        args_prefix: ["-rf", "build"]   # rm -rf build...
      - binary: rm
        args_regex: '-rf dist/\S+'       # full match against the arguments
```

`allow_patterns` (regular expressions over the whole command) still work, but
exempt the entire command when they match; `agentlint doctor` points them out.
Required rules ignore both.

## Exceptions

An exception allows one exact command for one rule in one repository, for at
most seven days. Use it for a specific, reviewed operation; for a class of
actions use an [approval](approvals-and-evidence.md#approvals).

```yaml
exceptions:
  - id: ticket-123
    rule_id: no-force-push
    repository: /absolute/path/to/repository
    operation: git push --force origin maintenance
    created_at: 2026-10-03T10:00:00Z
    expires_at: 2026-10-03T12:00:00Z
    reason: Approved maintenance window
```

Only literal simple commands qualify (no pipes, expansions or compound
commands). Required and organization rules can't be excepted. Each use is
recorded first in `~/.cache/agentlint/exception-audit.jsonl` (a SHA-256 of the
command, not the command); if that write fails, the rule still blocks.

## Repeated warnings

Hide a warning rule for the rest of a session with `agentlint suppress <rule>`
(`--list`, `--remove`, `--clear`), or automatically after N consecutive fires:

```yaml
rules:
  no-dead-imports:
    auto_suppress_after: 2
```

Errors are never suppressed.

### Circuit breaker

If an ERROR rule keeps firing, the circuit breaker lowers it step by step
(`ERROR → WARNING → INFO → off`) so a misfiring rule can't stall a session.
Degraded findings are labelled, a notice explains how to re-enable the rule,
and `agentlint report --summary` shows each rule's history. `no-secrets`,
`no-env-commit`, required rules and organization rules never degrade.

```yaml
circuit_breaker:
  enabled: true
  degraded_after: 3
  passive_after: 6
  open_after: 10
  reset_after_clean: 5
  reset_after_minutes: 30
  never_degrade: ["my-payment-validator"]
```

Per rule: `rules: {<rule>: {circuit_breaker: {...}}}`.

## Workspace policy

One policy can cover many repositories. Point the agent's environment at it:

```sh
export AGENTLINT_WORKSPACE_CONFIG=/path/to/workspace/agentlint.yml
```

It applies only to projects inside that file's directory and is combined with
each repository's own `agentlint.yml`: packs are added together, mappings merge,
and repository values win for scalars and lists.

```yaml
packs: [security, autopilot]
workspace:
  required_rules: [no-secrets, no-env-commit, no-force-push, cloud-resource-deletion]
```

Required rules stay enabled and blocking even if a repository disables them,
relaxes severity, ignores paths or uses inline ignores; a failure while
evaluating one also blocks. Per-rule path exemptions still apply, so review them
as policy decisions. A missing, invalid or shadowed workspace file fails closed.
This is local policy, not a tamper-proof sandbox.

`agentlint status` shows the layers in effect, and each denial names the layer
that made the rule active.

## Monorepos

`projects` sets packs per directory. The longest matching prefix wins; other
files use the top-level `packs`.

```yaml
projects:
  frontend/:
    packs: [frontend, react]
  backend/api/:
    packs: [python, security]
```

Core packs are added here too. `status` and `list-rules` show the top-level
configuration. Run CLI commands from the root or pass `--project-dir`.

## Evidence and approvals

```yaml
evidence:
  receipts_dirs: [~/.local/state/my-tool/receipts]   # receipts from other tools
  max_age: 24h
```

See [Approvals and evidence](approvals-and-evidence.md).

## Optional cloud and recording

`agentchute:` and `recording:` control the optional [AgentChute](agentchute.md)
connection and local session recordings. Both are off unless you enable them.

## AGENTS.md import

`agentlint import-agents-md` turns conventions in an [AGENTS.md](https://agents.md/)
file into configuration (`--dry-run` to preview, `--merge` to add to an existing
file). With `stack: auto`, AGENTS.md keywords can also enable extra packs.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `AGENTLINT_PROJECT_DIR` | Project directory, overriding the agent's |
| `AGENTLINT_WORKSPACE_CONFIG` | [Workspace policy](#workspace-policy) file |
| `AGENTLINT_SESSION_ID` | Session key for state shared between hook calls |
| `AGENTLINT_LOG_LEVEL` | Log level (default `WARNING`) |
| `AGENTLINT_CACHE_DIR` | Session state (default `~/.cache/agentlint/sessions`) |
| `AGENTLINT_HEARTBEAT_DIR` | Hook heartbeats used by `status` |
| `AGENTLINT_RECEIPTS_DIR` | Evidence receipts |
| `AGENTLINT_APPROVALS_FILE`, `AGENTLINT_APPROVAL_AUDIT_FILE` | Approvals and their audit log |
| `AGENTLINT_EXCEPTION_AUDIT_FILE` | Exception audit log |
| `AGENTLINT_RECORDING`, `AGENTLINT_RECORDINGS_DIR` | Local session recordings |
| `AGENTCHUTE_*`, `AGENTLINT_AGENTCHUTE_*`, `AGENTLINT_FEEDS_DIR` | [AgentChute](agentchute.md) settings and caches |

## Complete example

```yaml
severity: standard
packs: [python, security, autopilot]
# exclude_packs: [quality]
# custom_rules_dir: .agentlint/rules/

rules:
  ignore_paths: ["**/generated/**"]
  no-secrets:
    extra_prefixes: ["acme_live_"]
  max-file-size:
    limit: 500
  drift-detector:
    threshold: 15
  token-budget:
    max_tool_invocations: 200
  no-bash-file-write:
    allow_paths: ["*.log"]
  no-network-exfil:
    allowed_hosts: ["internal.example.com"]
  production-guard:
    allowed_projects: ["acme-staging"]
  no-destructive-commands:
    allow_operations:
      - { binary: rm, args_prefix: ["-rf", "build"] }
  cli-integration:
    commands:
      - name: ruff
        on: ["Write", "Edit"]
        glob: "**/*.py"
        command: "ruff check {file.path} --output-format=concise"

projects:
  web/:
    packs: [frontend, react]

evidence:
  max_age: 24h
```
