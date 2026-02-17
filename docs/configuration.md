# Configuration Reference

AgentLint is configured via `agentlint.yml` (or `agentlint.yaml`, `.agentlint.yml`) in your project root. Run `agentlint init` to generate one with auto-detected defaults.

## Top-level options

### `stack`

Controls how rule packs are activated.

- `auto` (default) — Detect from project files (pyproject.toml, package.json, etc.)
- Any other value — Use only the `universal` pack

### `severity`

Global severity mode. Transforms all violation severities:

| Mode | Effect |
|------|--------|
| `strict` | WARNING becomes ERROR, INFO becomes WARNING |
| `standard` | No transformation (default) |
| `relaxed` | WARNING becomes INFO |

### `packs`

Explicit list of rule packs to activate. Overrides auto-detection.

```yaml
packs:
  - universal
```

### `custom_rules_dir`

Path (relative to project root) containing custom rule `.py` files.

```yaml
custom_rules_dir: .agentlint/rules/
```

### `rules`

Per-rule configuration overrides. Each key is a rule ID.

```yaml
rules:
  no-secrets:
    enabled: false        # Disable the rule entirely
  max-file-size:
    limit: 300            # Override default (500)
  drift-detector:
    threshold: 5          # Override default (10)
```

## Universal rules reference

### `no-secrets` (PreToolUse, ERROR)

Blocks writes containing API keys, tokens, or passwords.

Detects patterns:
- Stripe keys (`sk_live_`, `sk_test_`)
- AWS keys (`AKIA...`)
- Generic API key assignments
- Bearer tokens
- Password string assignments

### `no-env-commit` (PreToolUse, ERROR)

Blocks writing `.env`, `.env.local`, `.env.production`, and similar credential files.

### `no-force-push` (PreToolUse, ERROR)

Blocks `git push --force` or `git push -f` to `main` or `master` branches.

### `no-destructive-commands` (PreToolUse, WARNING)

Warns on destructive shell commands:
- `rm -rf` (except safe targets like `node_modules`, `dist`, `__pycache__`)
- `DROP TABLE`, `DROP DATABASE`
- `git reset --hard`
- `git clean -fd`

### `dependency-hygiene` (PreToolUse, WARNING)

Warns on ad-hoc package installation:
- `pip install <package>` (but allows `pip install -e .`)
- `npm install <package>` (but allows `npm ci`, `npm install` with no args)

### `max-file-size` (PostToolUse, WARNING)

Warns when a written/edited file exceeds a line count threshold.

**Config options:**
- `limit` — Maximum lines (default: `500`)

### `drift-detector` (PostToolUse, WARNING)

Tracks file edits and test runs. Warns after N edits without running tests.

**Config options:**
- `threshold` — Edit count before warning (default: `10`)

### `no-debug-artifacts` (Stop, WARNING)

At session end, scans changed files for debug statements:
- JavaScript/TypeScript: `console.log()`, `debugger`
- Python: `print()`, `pdb.set_trace()`, `breakpoint()`

Skips test files.

### `test-with-changes` (Stop, WARNING)

At session end, warns if source files (`.py`, `.ts`, `.tsx`, `.js`, `.jsx`) were changed but no test files were updated.

Skips migrations, configs, and settings files.

### `no-todo-left` (Stop, INFO)

At session end, reports any `TODO`, `FIXME`, `HACK`, or `XXX` comments found in changed files.

## Full example

```yaml
stack: auto
severity: standard

packs:
  - universal

rules:
  no-secrets:
    enabled: true
  no-env-commit:
    enabled: true
  no-force-push:
    enabled: true
  no-destructive-commands:
    enabled: true
  dependency-hygiene:
    enabled: true
  max-file-size:
    limit: 500
  drift-detector:
    threshold: 10
  no-debug-artifacts:
    enabled: true
  test-with-changes:
    enabled: true
  no-todo-left:
    enabled: true

# custom_rules_dir: .agentlint/rules/
```
