# Rules

AgentLint ships 77 built-in rules in 8 packs. Every rule has a severity:

- **ERROR** blocks the action before it runs (PreToolUse) or is reported as a failure.
- **WARNING** is fed back to the agent as advice; the action proceeds.
- **INFO** appears in the session report.

Some rules emit more than one severity depending on what they find; their sections say so. `severity: strict` in `agentlint.yml` promotes warnings to errors, and `relaxed` demotes them to info.

To turn a rule off or tune it, see [Configuration](configuration.md#rules). To exempt one exact command for a limited time, see [exceptions](configuration.md#exceptions); to approve a class of action, see [approvals](approvals-and-evidence.md).

<!-- BEGIN GENERATED: overview (scripts/gen_docs.py) -->
| Pack | Rules | Activation |
|------|-------|------------|
| [universal](#universal) | 24 | Always active |
| [quality](#quality) | 7 | Always active |
| [python](#python) | 6 | Auto: `pyproject.toml` or `setup.py` |
| [frontend](#frontend) | 8 | Auto: `package.json` |
| [react](#react) | 3 | Auto: `react` in `package.json` dependencies |
| [seo](#seo) | 4 | Auto: an SSR/SSG framework in `package.json` (Next.js, Nuxt, Astro, ...) |
| [security](#security) | 7 | Opt-in |
| [autopilot](#autopilot) | 18 | Opt-in, experimental |
| **Total** | **77** | |
<!-- END GENERATED: overview -->

## Universal

Core safety and hygiene rules for any stack. Always active.

<!-- BEGIN GENERATED: pack-universal (scripts/gen_docs.py) -->
| Rule | Severity | Events | What it does |
|------|----------|--------|--------------|
| [`cicd-pipeline-guard`](#cicd-pipeline-guard) | ERROR | PreToolUse | Blocks edits to CI/CD pipeline files (.github/workflows, Jenkinsfile, etc.) without approval |
| [`cli-integration`](#cli-integration) | WARNING | PostToolUse | Run external CLI tools on file changes and report violations |
| [`dependency-hygiene`](#dependency-hygiene) | WARNING | PreToolUse | Suggests using lockfile-based tools instead of ad-hoc pip/npm install |
| [`drift-detector`](#drift-detector) | WARNING | PreToolUse, PostToolUse | Warns when many edits happen without running tests |
| [`file-scope`](#file-scope) | ERROR | PreToolUse | Restricts file access based on allow/deny glob patterns |
| [`git-checkpoint`](#git-checkpoint) | INFO | PreToolUse, Stop | Creates a git safety checkpoint before destructive operations |
| [`max-file-size`](#max-file-size) | WARNING | PostToolUse | Warns when a file exceeds a configurable line-count limit after Write/Edit |
| [`no-compromised-dependency`](#no-compromised-dependency) | ERROR | PreToolUse | Blocks install of packages on the AgentChute cloud-curated compromised-packages deny list. Self-degrades to no-op when AgentChute is not configured |
| [`no-debug-artifacts`](#no-debug-artifacts) | WARNING | Stop | Detects leftover debug statements (console.log, print, debugger, breakpoint) |
| [`no-destructive-commands`](#no-destructive-commands) | WARNING | PreToolUse | Warns on destructive commands like rm -rf, DROP TABLE, git reset --hard |
| [`no-env-commit`](#no-env-commit) | ERROR | PreToolUse | Prevents writing to .env files that may contain secrets |
| [`no-force-push`](#no-force-push) | ERROR | PreToolUse | Prevents force-pushing to main or master branches |
| [`no-nvd-critical-cve-install`](#no-nvd-critical-cve-install) | ERROR | PreToolUse | Blocks explicit package installs or container pulls when AgentChute's cached NVD feed has an exact critical CVE CPE product+version match |
| [`no-push-to-main`](#no-push-to-main) | WARNING | PreToolUse | Warns on direct push to main or master branches |
| [`no-secrets`](#no-secrets) | ERROR | PreToolUse | Prevents writing secrets or credentials into source files |
| [`no-skip-hooks`](#no-skip-hooks) | WARNING | PreToolUse | Warns on git commit --no-verify or --no-gpg-sign |
| [`no-test-weakening`](#no-test-weakening) | WARNING | PreToolUse | Warns when tests are skipped, trivialized, or commented out |
| [`no-todo-left`](#no-todo-left) | INFO | Stop | Detects leftover TODO/FIXME/HACK/XXX comments in changed files |
| [`no-vulnerable-import`](#no-vulnerable-import) | WARNING | PreToolUse | Warns when source code imports a package that has open GHSA advisories. Verify your locked version is past the fix |
| [`no-vulnerable-version-install`](#no-vulnerable-version-install) | ERROR | PreToolUse | Blocks install of a specific package version when GHSA reports it as vulnerable. Pinned installs only (e.g. `npm i foo@1.2.3`); unpinned installs are handled by `dependency-hygiene` |
| [`package-publish-guard`](#package-publish-guard) | ERROR | PreToolUse | Blocks npm publish, twine upload, gem push, cargo publish, and similar registry pushes |
| [`test-with-changes`](#test-with-changes) | WARNING | Stop | Warns when source files are changed but no test files were updated |
| [`token-budget`](#token-budget) | WARNING | PostToolUse, Stop | Tracks session activity and warns on excessive tool invocations |
| [`token-burn-against-team-budget`](#token-burn-against-team-budget) | WARNING | PostToolUse, Stop | Warns or blocks token-heavy AI operations when the team's cloud-aggregated monthly spend has hit warning or budget-cap thresholds. Self-degrades to no-op when AgentChute is not configured |
<!-- END GENERATED: pack-universal -->

### `cicd-pipeline-guard`

Blocks modifications to CI/CD pipeline files (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, etc.) without a session-level confirmation key. Prevents accidental pipeline changes during autonomous sessions.

### `cli-integration`

Runs external CLI tools on file changes and reports non-zero exit codes as violations. Configure commands with template placeholders.

**Global defaults:** Top-level keys apply to all commands. Per-command keys override:

```yaml
rules:
  cli-integration:
    timeout: 15           # default for all commands
    severity: warning     # default for all commands
    diff_only: true       # default for all commands — filter to changed lines only
    max_output: 1000      # default for all commands
    on: ["Write", "Edit"] # default for all commands
    commands:
      - name: ruff
        glob: "**/*.py"
        command: "ruff check {file.path} --output-format=concise"
        timeout: 30       # override for ruff only

      - name: mypy
        glob: "**/*.py"
        command: "mypy {file.path}"
        # inherits timeout: 15, diff_only: true from global

      - name: pip-audit
        glob: "**/requirements*.txt"
        command: "pip-audit -r {file.path}"
        timeout: 30
        severity: warning

      - name: pytest-related
        glob: "src/**/*.py"
        command: "pytest tests/ -k {file.stem} -x -q --tb=short"
        timeout: 60
        severity: info
```

**`diff_only` mode:** When `true`, CLI output is filtered to only violations on changed lines (using the diff between pre-edit and post-edit file content). Pre-existing violations are suppressed. Works with any CLI tool that reports `:LINE:` format (ruff, mypy, eslint, etc.).

**`auto-fix` mode:** For deterministic fixers like `ruff format`, `prettier`, or `black`, set `mode: auto-fix` to run the fixer silently on every Write/Edit. No violation is created on success — only on actual failure (crash, timeout):

```yaml
rules:
  cli-integration:
    commands:
      - name: ruff-format
        command: "ruff format {file.path}"
        glob: "**/*.py"
        mode: auto-fix     # run silently, apply fix, no warning
      - name: prettier
        command: "prettier --write {file.path}"
        glob: "**/*.{ts,tsx,js,jsx}"
        mode: auto-fix
```

Valid modes: `check` (default — report violations), `auto-fix` (run silently, warn only on failure).

**Note:** `diff_only` is ignored when `mode: auto-fix` — fixers always run on the full file.

**Available placeholders:**

| Placeholder | Value | Example |
|---|---|---|
| `{file.path}` | Absolute file path | `/home/user/project/src/app.py` |
| `{file.relative}` | Relative to project | `src/app.py` |
| `{file.name}` | Filename | `app.py` |
| `{file.stem}` | Filename without extension | `app` |
| `{file.ext}` | Extension | `py` |
| `{file.dir}` | Parent directory | `/home/user/project/src` |
| `{file.dir.relative}` | Parent dir (relative) | `src` |
| `{project.dir}` | Project root | `/home/user/project` |
| `{tool.name}` | Tool that triggered | `Write` |
| `{session.changed_files}` | All changed files (space-separated) | `src/a.py src/b.py` |
| `{env.VARNAME}` | Environment variable | _(value of $VARNAME)_ |

**Security:** All placeholder values are shell-escaped via `shlex.quote()`. File paths outside the project directory are rejected. Commands with unresolvable placeholders are silently skipped.

### `dependency-hygiene`

Warns on ad-hoc package installation:
- `pip install <package>` (but allows `pip install -e .`)
- `npm install <package>` (but allows `npm ci`, `npm install` with no args)

### `drift-detector`

Tracks file edits and test runs. Fires through two channels:

1. **Mid-session** (PostToolUse): warns once after N unique file edits
   without running tests, then stays silent until tests are run.
2. **Commit boundary** (PreToolUse): fires once per
   `git commit` attempt when the agent has crossed the threshold without
   running tests. `git commit --amend --no-edit` is skipped (no new
   content). Resets after a successful test run. A fresh
   evidence receipt (written by AgentLint or another tool) newer than the
   last edit also satisfies the check, and the warning cites the latest
   evidence.

Test runs are recognized from parsed operations (`uv run pytest`,
`python -m pytest`, `make test`, npm/pnpm/yarn test, vitest, jest, go test,
cargo test), including redirected output; `echo pytest` is not a run, and a run
the agent reports as failed does not reset the counter.

Only counts code files — config files (`.yml`, `.md`, etc.) are excluded.

**Config options:**
- `threshold` — Unique file edit count before warning (default: `15`)
- `extensions` — List of file extensions to count (default: `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.rs`, `.go`, `.rb`, `.java`, `.kt`, `.swift`, `.c`, `.cpp`, `.h`, `.cs`, `.ex`, `.vue`, `.svelte`)

### `file-scope`

Restricts which files the agent can read/write based on allow/deny glob patterns. If no `file-scope` config is present, the rule is inactive (zero-config = no restrictions).

```yaml
rules:
  file-scope:
    allow: ["src/**", "tests/**", "docs/**"]
    deny: ["*.env", "credentials/**", ".github/workflows/**", "/etc/**"]
    deny_message: "File access denied by governance policy"
```

**Config options:**
- `allow` — Glob patterns for allowed files. If present, only matching files are accessible.
- `deny` — Glob patterns for denied files. Deny takes precedence over allow.
- `deny_message` — Custom message shown when access is denied (default: "File access denied by file-scope rule")

**Behavior:**
- Blocks Write, Edit, Read tool calls and Bash file operations (cat, rm, cp, mv)
- Path traversal (`../`) blocked via `os.path.realpath()`
- Matches against resolved path, original path, relative path, and basename
- Files outside the project directory are matched against absolute path patterns

### `git-checkpoint`

*PreToolUse + Stop, INFO — disabled by default*

Creates a git safety checkpoint (`git stash push`) before destructive operations. At session end, cleans up old checkpoints. **Opt-in** — must be explicitly enabled.

**Config options:**
- `enabled` — Enable the rule (default: `false`)
- `cleanup_hours` — Remove checkpoints older than N hours (default: `24`)
- `triggers` — Custom list of regex patterns that trigger checkpoints (overrides defaults)

**Default triggers:** `rm -rf`, `git reset --hard`, `git checkout .`, `git clean -fd`, `DROP TABLE`, `DROP DATABASE`

```yaml
rules:
  git-checkpoint:
    enabled: true
    cleanup_hours: 48
    # Custom triggers (overrides defaults):
    # triggers:
    #   - "\\bmy-dangerous-cmd\\b"
```

### `max-file-size`

Warns when a file crosses the line-count threshold. Only fires when a file **grows past** the limit — editing a pre-existing large file does not trigger. Shows `+N over` in the message with an actionable suggestion.

**Config options:**
- `limit` — Maximum lines (default: `500`)
- `allow_paths` — Skip this rule for matching files (e.g., `["**/hybrid_parser.py"]`)

### `no-compromised-dependency`

Blocks `npm`/`pip`/`gem`-style installs of packages on a curated list of known-compromised packages (supply-chain attacks). The universal `dependency-hygiene` warning still applies either way.

Uses cached data from the optional [AgentChute](agentchute.md) feeds. Without AgentChute configured, this rule does nothing.

### `no-debug-artifacts`

At session end, scans changed files for debug statements:
- JavaScript/TypeScript: `console.log()`, `debugger`
- Python: `print()`, `pdb.set_trace()`, `breakpoint()`

Skips test files.

### `no-destructive-commands`

*PreToolUse, WARNING/ERROR*

Warns on destructive shell commands. Some patterns escalate to ERROR severity:

**WARNING:**
- `rm -rf` (except safe build-artifact targets like `node_modules`, `dist`,
  `__pycache__`, **and ephemeral paths under `/tmp/`, `/var/folders/`,
  `/private/tmp/`**)
- `DROP TABLE`, `DROP DATABASE`
- `git reset --hard`, `git clean -fd`
- `chmod 777` (overly permissive)
- `docker system prune -a --volumes`
- `kubectl delete namespace`

**ERROR (catastrophic):**
- `rm -rf /` or `rm -rf ~` (root/home deletion) — fires even when the
  ephemeral path exemption would otherwise apply.
- `mkfs` (filesystem format)
- `dd if=/dev/zero` (disk wipe)
- Fork bombs
- `git branch -D main/master` (protected branch deletion)

**Config options:**
- `safe_rm_targets: list[str]` — extend the safe-basename set.
- `safe_path_prefixes: list[str]` — extend the safe-prefix set
  (defaults: `/tmp/`, `/var/folders/`, `/private/tmp/`).
- `allow_patterns: list[str]` — regex allowlist that short-circuits the
  whole rule when matched.

### `no-env-commit`

Blocks writing `.env`, `.env.local`, `.env.production`, and similar credential files. Also detects Bash commands that write to `.env` files (e.g. `echo "SECRET=val" > .env`, `cp .env.example .env`, `tee .env`, `sed -i ... .env`).

### `no-force-push`

Blocks `git push --force` or `git push -f` to `main` or `master` branches.

### `no-nvd-critical-cve-install`

Blocks explicit pinned installs (npm/yarn/pnpm, pip, cargo, apt) and container image pulls that exactly match a critical NVD CVE record's CPE data.

Uses cached data from the optional [AgentChute](agentchute.md) feeds. Without AgentChute configured, this rule does nothing.

### `no-push-to-main`

Warns on direct `git push` to `main` or `master` branches (excluding force pushes, which are handled by `no-force-push`).

### `no-secrets`

Blocks writes containing API keys, tokens, or passwords.

Detects patterns:
- Stripe keys (`sk_live_`, `sk_test_`)
- AWS keys (`AKIA...`)
- GitHub tokens (`ghp_`, `github_pat_`)
- Slack tokens (`xoxb-`, `xoxp-`)
- Generic API key assignments
- Bearer tokens and JWTs
- Password string assignments
- Private keys (RSA, EC, DSA)
- Database connection strings with credentials
- GCP service account files
- Terraform state files
- Sensitive filenames (`.npmrc`, `credentials.json`, etc.)
- Curl with authentication (`-u`, `-H "Authorization: ..."`)

**Config options:**
- `extra_prefixes` — Additional token prefixes to detect (e.g. `["myco_secret_"]`)

### `no-skip-hooks`

Warns when git commands use `--no-verify` or `--no-gpg-sign` flags to skip safety hooks.

### `no-test-weakening`

Detects patterns that weaken test suites when writing to test files:
- Skip markers (`@pytest.mark.skip`, `@unittest.skip`, `it.skip()`, `describe.skip()`)
- Trivially passing assertions (`assert True`, `assertTrue(True)`, `expect(true).toBe(true)`)
- Commented-out assertions (`# assert ...`, `// expect(...)`)
- `@pytest.mark.xfail` without a reason
- Empty test functions (`def test_...: pass`)

### `no-todo-left`

At session end, reports any `TODO`, `FIXME`, `HACK`, or `XXX` comments found in changed files.

### `no-vulnerable-import`

Warns when new code imports or requires a package that currently has open GHSA advisories (JS/TS `import`/`require`, Python `import`/`from`). Imports carry no version, so this is a prompt to check your locked version, not proof of exposure.

Uses cached data from the optional [AgentChute](agentchute.md) feeds. Without AgentChute configured, this rule does nothing.

### `no-vulnerable-version-install`

Blocks pinned installs (`pkg@1.2.3`, `pkg==1.2.3`) of versions that fall inside a GitHub Security Advisory (GHSA) vulnerable range.

Uses cached data from the optional [AgentChute](agentchute.md) feeds. Without AgentChute configured, this rule does nothing.

### `package-publish-guard`

Blocks package publish commands: `npm publish`, `twine upload`, `gem push`, `cargo publish`. Prevents accidental releases during automated sessions.

### `test-with-changes`

At session end, warns if source files (`.py`, `.ts`, `.tsx`, `.js`, `.jsx`) were changed but no test files were updated.

Skips migrations, configs, and settings files.

### `token-budget`

*PostToolUse + Stop, WARNING/INFO*

Tracks session activity (tool invocations, content bytes, duration). Warns at configurable threshold.

The budget counts **file-changing** calls (`Write`, `Edit`,
`MultiEdit`, `NotebookEdit`; Codex `apply_patch` arrives as these) by default.
Shell and read calls still appear in the Stop summary but do not move a session
toward the mid-session "consider wrapping up" warning, so long verification
work (tests, git, CI checks) is not nudged to stop early.

**Config options:**
- `count_tools` — Tools that count toward the budget: a list of tool names, or `all` (default: file-changing tools)
- `max_tool_invocations` — Maximum counted tool calls before warning (default: `200`)
- `max_content_bytes` — Maximum content bytes (default: `500000`)
- `warn_at_percent` — Warning threshold (default: `80`)

### `token-burn-against-team-budget`

Warns (PostToolUse and Stop) when your team's AgentChute budget status reports pressure: WARNING at 80% used, ERROR at 100%.

Uses cached data from the optional [AgentChute](agentchute.md) feeds. Without AgentChute configured, this rule does nothing. For a local, per-session limit see [`token-budget`](#token-budget).

## Quality

Code-review style checks. Always active.

<!-- BEGIN GENERATED: pack-quality (scripts/gen_docs.py) -->
| Rule | Severity | Events | What it does |
|------|----------|--------|--------------|
| [`commit-message-format`](#commit-message-format) | WARNING | PreToolUse | Validates commit messages follow conventional format |
| [`naming-conventions`](#naming-conventions) | INFO | PreToolUse | Checks file names against language-specific naming conventions |
| [`no-dead-imports`](#no-dead-imports) | INFO | PostToolUse | Detects unused imports in Python and JS/TS files |
| [`no-error-handling-removal`](#no-error-handling-removal) | WARNING | PreToolUse | Warns when error handling patterns (try/except, .catch) are removed |
| [`no-file-creation-sprawl`](#no-file-creation-sprawl) | WARNING | PostToolUse | Warns when too many new files are created in a session |
| [`no-large-diff`](#no-large-diff) | WARNING | PostToolUse | Warns when a single edit adds or removes too many lines |
| [`self-review-prompt`](#self-review-prompt) | INFO | Stop | Injects a self-review prompt at session end to catch bugs |
<!-- END GENERATED: pack-quality -->

### `commit-message-format`

Validates git commit messages follow conventional format. Supports both simple `-m "message"` and heredoc format (`-m "$(cat <<'EOF'...EOF)"`).

**Config options:**
- `max_subject_length` — Maximum subject line length (default: `72`)
- `format` — Format to enforce: `"conventional"` (default) or `"freeform"` (skip format check)

```yaml
rules:
  commit-message-format:
    max_subject_length: 100    # override default 72
    format: conventional       # or "freeform" to skip type prefix check
```

### `naming-conventions`

Checks file names against language-specific conventions (snake_case for Python, camelCase for TS/JS, PascalCase for TSX/JSX). Accepts kebab-case as alternative for TSX/JSX. Exempts test files, migration files, `index`, `__init__`, and common config files.

**Config options:**
- `python` — Convention for .py files (default: `"snake_case"`)
- `typescript` — Convention for .ts/.js files (default: `"camelCase"`)
- `react_components` — Convention for .tsx/.jsx files (default: `"PascalCase"`)
- `migration_paths` — Path markers for migration file exemption (default: `["migration", "alembic", "versions"]`)

### `no-dead-imports`

Detects unused imports in Python and JS/TS files after Write/Edit. Uses a grace period by default to avoid false positives during multi-edit workflows — violations only fire if imports are still unused after a subsequent edit to the same file.

**Config options:**
- `grace_period` — Defer violations until 2nd consecutive edit to same file (default: `true`)
- `ignore_files` — File basenames to skip, typically re-export files (default: `["__init__.py", "index.ts", "index.js", "index.tsx", "index.jsx"]`)

### `no-error-handling-removal`

Warns when error handling patterns (`try/except`, `.catch()`, null checks) are removed from existing code. Uses diff-based detection via `file_content_before`.

### `no-file-creation-sprawl`

Warns when too many new files are created in a single session. Files
under common categories that legitimately proliferate (tests, docs,
migrations) are exempt by default so the counter reflects real source-
file sprawl rather than routine additions.

**Config options:**
- `max_new_files` — Maximum new files before warning (default: `10`)
- `exempt_paths` — Path fragments that bypass the counter
  (default: `["tests/", "test/", "docs/", "alembic/versions/",
  "migrations/versions/", "spec/", "__tests__/"]`). Custom values
  extend (don't replace) the defaults.

### `no-large-diff`

Warns when a single Write/Edit adds or removes too many lines. Test
files, non-code files (`.md`, `.yml`, `.json`, etc.), and migration
files (`alembic/versions/`, `migrations/versions/`, `db/migrate/`) are
exempt by default — a single migration is one conceptual unit even at
200+ lines.

**Config options:**
- `max_lines_added` — Maximum lines added (default: `200`)
- `max_lines_removed` — Maximum lines removed (default: `100`)
- `exempt_test_files` — Skip test files (default: `true`)
- `test_file_patterns` — Glob patterns matching test file basenames (default: `["test_*", "*_test.*", "*.spec.*", "*.test.*", "*_spec.*", "conftest.py"]`)
- `migration_paths` — Path fragments for migration exemption
  (default: `["alembic/versions/", "migrations/versions/", "db/migrate/"]`).
  Honors a top-level `migration_paths` global config too — same key as
  `no-dangerous-migration` so you only configure it once.

### `self-review-prompt`

Injects an adversarial self-review prompt at session end to catch bugs.

## Python

Activates automatically when `pyproject.toml` or `setup.py` exists.

<!-- BEGIN GENERATED: pack-python (scripts/gen_docs.py) -->
| Rule | Severity | Events | What it does |
|------|----------|--------|--------------|
| [`no-bare-except`](#no-bare-except) | WARNING | PreToolUse | Prevents bare except: clauses that catch all exceptions |
| [`no-dangerous-migration`](#no-dangerous-migration) | WARNING | PreToolUse | Warns about dangerous database migration operations |
| [`no-sql-injection`](#no-sql-injection) | ERROR | PreToolUse | Prevents SQL injection via string interpolation |
| [`no-unnecessary-async`](#no-unnecessary-async) | INFO | PostToolUse | Flags async functions that don't use await |
| [`no-unsafe-shell`](#no-unsafe-shell) | ERROR | PreToolUse | Prevents unsafe shell execution via subprocess with shell=True |
| [`no-wildcard-import`](#no-wildcard-import) | WARNING | PreToolUse | Prevents wildcard imports that pollute the namespace |
<!-- END GENERATED: pack-python -->

### `no-bare-except`

Prevents bare `except:` clauses that catch all exceptions including `SystemExit` and `KeyboardInterrupt`.

**Config options:**
- `allow_reraise` — Allow bare except if it contains a bare `raise` (default: `true`)

### `no-dangerous-migration`

Warns about dangerous database migration operations in Alembic migration
files (dropping columns, renaming tables, etc.).

**Scope-aware:** operations are evaluated within their
enclosing function. An `op.drop_column()` or `op.drop_table()` inside
`def downgrade()` is the expected inverse of an upgrade and does not
fire — tests and rollback workflows depend on it. The rule still warns
when an `upgrade()` performs an irreversible operation without a
corresponding `create_table()` *in `downgrade()`*. Falls back to whole-
file scanning on `SyntaxError` so malformed migrations still get
best-effort checks rather than crashing.

**Config options:**
- `migration_paths` — Custom path markers for migration files (default: detects `migration`, `alembic`, `versions` in path)
- `require_timezone` — Enforce `timezone=True` on DateTime columns (default: `true`)

### `no-sql-injection`

Blocks SQL queries built via string interpolation (f-strings, `.format()`, `%` operator, concatenation).

**Config options:**
- `extra_keywords` — Additional SQL keywords to detect beyond `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`

### `no-unnecessary-async`

Flags `async def` functions that never use `await`. Skips test files and stub/abstract implementations.

**Config options:**
- `ignore_decorators` — Additional decorator names to skip (default: merges with `property`, `override`, `abstractmethod`)

### `no-unsafe-shell`

Blocks unsafe shell execution via `subprocess` with `shell=True` and `os` module shell functions.

**Config options:**
- `allow_shell_true` — Allow subprocess calls with `shell=True` (default: `false`)

### `no-wildcard-import`

Prevents `from module import *` which pollutes the namespace and makes dependencies unclear.

**Config options:**
- `allow_in` — Files where wildcard imports are allowed (default: `["__init__.py"]`)

## Frontend

Accessibility, mobile and styling checks. Activates automatically when `package.json` exists.

<!-- BEGIN GENERATED: pack-frontend (scripts/gen_docs.py) -->
| Rule | Severity | Events | What it does |
|------|----------|--------|--------------|
| [`a11y-form-labels`](#a11y-form-labels) | WARNING | PreToolUse | Ensures form inputs have associated labels |
| [`a11y-heading-hierarchy`](#a11y-heading-hierarchy) | INFO | PreToolUse | Ensures proper heading hierarchy |
| [`a11y-image-alt`](#a11y-image-alt) | WARNING | PreToolUse | Ensures images have alt text for accessibility |
| [`a11y-interactive-elements`](#a11y-interactive-elements) | WARNING | PreToolUse | Ensures interactive elements have proper ARIA attributes |
| [`mobile-responsive-patterns`](#mobile-responsive-patterns) | INFO | PreToolUse | Warns about desktop-only layout patterns |
| [`mobile-touch-targets`](#mobile-touch-targets) | WARNING | PreToolUse | Ensures interactive elements meet minimum touch target size |
| [`style-focus-visible`](#style-focus-visible) | WARNING | PreToolUse | Ensures focus indicators are not removed without replacement |
| [`style-no-arbitrary-values`](#style-no-arbitrary-values) | INFO | PreToolUse | Warns about arbitrary Tailwind values that bypass design tokens |
<!-- END GENERATED: pack-frontend -->

### `a11y-form-labels`

Ensures form inputs have associated `<label>` elements or `aria-label` attributes (WCAG 1.3.1).

### `a11y-heading-hierarchy`

Ensures proper heading hierarchy — no multiple `<h1>` elements and no skipped heading levels.

**Config options:**
- `max_h1` — Maximum number of `<h1>` elements per page (default: `1`)

### `a11y-image-alt`

Ensures images have `alt` text for screen readers (WCAG 1.1.1).

**Config options:**
- `extra_components` — Additional image component names beyond `img` and `Image`

### `a11y-interactive-elements`

Ensures interactive elements have proper ARIA attributes. Detects link anti-patterns like "click here".

**Config options:**
- `link_anti_patterns` — Custom anti-pattern phrases (default: `click here`, `read more`, `learn more`, `here`)

### `mobile-responsive-patterns`

Warns about desktop-only layout patterns: large grids without responsive breakpoints, fixed widths, and hover-only interactions.

**Config options:**
- `min_grid_cols_warning` — Minimum grid columns that trigger a warning (default: `4`)

### `mobile-touch-targets`

Ensures interactive elements meet minimum touch target size of 44x44 CSS pixels (WCAG 2.5.5).

### `style-focus-visible`

Ensures focus indicators (`outline`, `ring`) are not removed without replacement. Checks for `outline: none` or `outline-none` without a `focus-visible` or `focus:ring` alternative (WCAG 2.4.7).

### `style-no-arbitrary-values`

Warns about arbitrary Tailwind CSS values (e.g. `w-[347px]`, `text-[#1a2b3c]`) that bypass design tokens.

## React

Activates automatically when `react` is a dependency in `package.json`.

<!-- BEGIN GENERATED: pack-react (scripts/gen_docs.py) -->
| Rule | Severity | Events | What it does |
|------|----------|--------|--------------|
| [`react-empty-state`](#react-empty-state) | INFO | PreToolUse | Suggests adding empty state handling for array.map() in JSX |
| [`react-lazy-loading`](#react-lazy-loading) | INFO | PreToolUse | Suggests lazy loading for heavy components in page files |
| [`react-query-loading-state`](#react-query-loading-state) | WARNING | PreToolUse | Ensures useQuery/useMutation results handle loading and error states |
<!-- END GENERATED: pack-react -->

### `react-empty-state`

Suggests adding empty state handling when `array.map()` is used in JSX without a corresponding length/empty check.

### `react-lazy-loading`

Suggests `React.lazy()` for heavy components imported in page-level files. Ensures `<Suspense>` wraps lazy-loaded components.

**Config options:**
- `heavy_components` — Custom component names considered heavy (default: `Chart`, `DataTable`, `Editor`, `Calendar`, `Map`, `RichTextEditor`, `CodeEditor`, `Spreadsheet`)
- `page_patterns` — Custom path patterns for page files (default: `pages/`, `app/`, `routes/`)

### `react-query-loading-state`

Ensures `useQuery` / `useSuspenseQuery` results destructure and handle `isLoading` and `isError` (or `error`) states.

**Config options:**
- `hooks` — Custom query hook names (default: `useQuery`, `useSuspenseQuery`)

## SEO

Activates automatically when an SSR/SSG framework (Next.js, Nuxt, Gatsby, Astro, SvelteKit, Remix) is a dependency.

<!-- BEGIN GENERATED: pack-seo (scripts/gen_docs.py) -->
| Rule | Severity | Events | What it does |
|------|----------|--------|--------------|
| [`seo-open-graph`](#seo-open-graph) | INFO | PreToolUse | Ensures pages with metadata also include Open Graph tags |
| [`seo-page-metadata`](#seo-page-metadata) | WARNING | PreToolUse | Ensures page files include title and description metadata |
| [`seo-semantic-html`](#seo-semantic-html) | INFO | PreToolUse | Encourages use of semantic HTML elements |
| [`seo-structured-data`](#seo-structured-data) | INFO | PreToolUse | Suggests adding JSON-LD structured data to content pages |
<!-- END GENERATED: pack-seo -->

### `seo-open-graph`

Ensures pages that have metadata also include Open Graph (`og:`) tags for social media previews.

**Config options:**
- `required_properties` — Required OG properties (default: `og:title`, `og:description`, `og:image`)

### `seo-page-metadata`

Ensures page files include `<title>` and meta description. Detects framework-specific patterns (Next.js `generateMetadata`, Nuxt `useHead`, etc.).

**Config options:**
- `page_patterns` — Custom page path patterns (default: `pages/`, `app/`, `routes/`)
- `metadata_components` — Additional metadata component names

### `seo-semantic-html`

Encourages semantic HTML elements (`<main>`, `<nav>`, `<article>`, `<section>`) over excessive `<div>` usage.

**Config options:**
- `min_div_threshold` — Minimum number of `<div>` elements before warning (default: `10`)

### `seo-structured-data`

Suggests adding JSON-LD structured data (`<script type="application/ld+json">`) to content pages.

**Config options:**
- `content_path_patterns` — Path patterns for content pages (default: `product`, `article`, `blog`, `post`, `recipe`, `event`)

## Security

Opt-in. Closes the common escape hatch of writing files or sending data through the shell instead of the agent's file tools. Add `security` to `packs:`.

<!-- BEGIN GENERATED: pack-security (scripts/gen_docs.py) -->
| Rule | Severity | Events | What it does |
|------|----------|--------|--------------|
| [`env-credential-reference`](#env-credential-reference) | WARNING | PreToolUse | Warns when *_FILE env vars reference local paths (credential leakage risk) |
| [`no-bash-file-write`](#no-bash-file-write) | ERROR | PreToolUse | Blocks file writes via Bash (cat >, tee, sed -i, cp, heredocs, etc.) |
| [`no-blocked-domain-fetch`](#no-blocked-domain-fetch) | WARNING | PreToolUse | Warns when `curl/wget/fetch/http` targets a domain on the AgentChute cloud-curated StevenBlack/hosts deny-list (ads/trackers/malware/etc). Self-degrades to no-op when AgentChute is not configured |
| [`no-compromised-action`](#no-compromised-action) | ERROR | PreToolUse | Blocks GitHub Actions `uses: <owner/repo>@<ref>` in workflow files when the action has open GHSA advisories. Self-degrades to no-op when AgentChute is not configured |
| [`no-leaked-secret-pattern`](#no-leaked-secret-pattern) | ERROR | PreToolUse | Blocks writes that contain leaked-secret patterns from the AgentChute cloud-curated gitleaks ruleset. Self-degrades to no-op when AgentChute is not configured |
| [`no-malicious-url-fetch`](#no-malicious-url-fetch) | ERROR | PreToolUse | Blocks `curl/wget/fetch/http` to URLs on the AgentChute cloud-curated URLhaus deny-list. Self-degrades to no-op when AgentChute is not configured |
| [`no-network-exfil`](#no-network-exfil) | ERROR | PreToolUse | Blocks potential data exfiltration via curl, nc, scp, etc |
<!-- END GENERATED: pack-security -->

### `env-credential-reference`

Warns when environment variable patterns reference local file paths (e.g., `DATABASE_URL_FILE=/etc/secrets/db`), which may indicate credential leakage risk.

### `no-bash-file-write`

Blocks file writes via Bash commands, enforcing use of the Write/Edit
tools instead. Detects: `cat >`, `echo >`, `tee`, `sed -i`, `cp`, `mv`,
`perl -pi`, `awk >`, `dd of=`, `python -c ... open(...).write()`, and
heredocs.

For a simple, literal `python -c CODE` command, Python syntax is inspected
without executing code or importing modules. `Path(...)` construction,
`read_text()` / `read_bytes()`, and `open()` with its default mode or a literal
`r`, `rb`, `rt`, `br`, or `tr` mode are allowed. This includes imported aliases
for `builtins.open` and `io.open`, and pathlib's `open()` method. Write modes,
unknown modes, unpacked arguments, opener references passed or assigned to
other functions, known write methods, and dynamic execution remain blocked.
Reflective builtin access through `globals`, `locals`, `vars`, `__builtins__`,
or `__dict__`, and calls to string-keyed openers also remain conservative.
Known `os` / `shutil` file-changing APIs and process-spawning calls through
`os.system`, `os.popen`, and `subprocess` are blocked, including imported aliases.
This is a check for visible file operations, not proof that imported functions
are pure or a general Python sandbox.

Recognized invocations use `python`, `python2`, `python3`, or versioned names
such as `python3.13`, optionally with a directory prefix, literal `env` /
`command` wrappers, and separate `-B`, `-E`, `-I`, `-O`, `-OO`, `-q`, `-s`,
`-S`, or `-u` flags before `-c`. Other flags, combined flags, attached `-c`
arguments, shell expansions, compound commands, redirects, invalid Python,
and source larger than 64 KiB retain conservative text detection. Python
write destinations are not extracted: an unrelated shell redirect to an
allowed or scratch path cannot exempt a Python write, and Python writes do
not receive path exemptions.

Writes targeting **ephemeral/scratch paths** (`/tmp/`, `/var/folders/`,
`/private/tmp/`) are exempt by default — these are not
project source files. Cloud CLI binaries (`bq`, `aws`, `kubectl`, ...)
are also recognized so their `cp`/`mv` subcommands don't fire.

**Config options:**
- `allow_paths` — Glob patterns for allowed write targets (e.g. `["*.log"]`)
- `allow_patterns` — Regex patterns for allowed commands (e.g. `["echo.*>>.*\\.log"]`)
- `safe_path_prefixes` — Extra ephemeral prefixes (extends, doesn't
  replace, the built-in safe set)
- `safe_binaries` — Extra CLI tool names whose subcommands are not
  shell file ops (extends `KNOWN_CLI_TOOLS`)

### `no-blocked-domain-fetch`

Warns on fetches from domains in the StevenBlack hosts deny-list (malware, ads, trackers). Broader and noisier than [`no-malicious-url-fetch`](#no-malicious-url-fetch), hence WARNING.

Uses cached data from the optional [AgentChute](agentchute.md) feeds. Without AgentChute configured, this rule does nothing.

### `no-compromised-action`

Blocks edits to GitHub Actions workflows that reference (`uses: owner/repo@ref`) an action with a GHSA advisory covering that ref. SHA-pinned refs produce a warning because the SHA alone can't be checked against the advisory range.

Uses cached data from the optional [AgentChute](agentchute.md) feeds. Without AgentChute configured, this rule does nothing.

### `no-leaked-secret-pattern`

Runs the cloud-curated gitleaks pattern set (about 220 vendor-specific secret formats) against new file content. Complements the offline [`no-secrets`](#no-secrets) prefixes.

Uses cached data from the optional [AgentChute](agentchute.md) feeds. Without AgentChute configured, this rule does nothing.

### `no-malicious-url-fetch`

Blocks `curl`/`wget`/similar fetches of URLs listed as malicious by URLhaus (prefix match, so appended query strings don't evade it).

Uses cached data from the optional [AgentChute](agentchute.md) feeds. Without AgentChute configured, this rule does nothing.

### `no-network-exfil`

Blocks potential data exfiltration via network commands. Detects: `curl POST/PUT` with data, `curl -d @file`, piping secrets to curl, `nc` with sensitive files, `scp` of credential files, `wget --post-file`, `python requests.post()`, and `rsync` of sensitive files to remote.

Default allowed hosts: `github.com`, `pypi.org`, `registry.npmjs.org`, `rubygems.org`.

**Config options:**
- `allowed_hosts` — Additional allowed destination hosts

## Autopilot

Opt-in and **experimental**: guardrails for agents that operate cloud and infrastructure tools (gcloud, aws, kubectl, terraform, ssh). These are pattern-based heuristics; expect false positives and false negatives, and do not treat them as a production authorization system. Add `autopilot` to `packs:`.

<!-- BEGIN GENERATED: pack-autopilot (scripts/gen_docs.py) -->
| Rule | Severity | Events | What it does |
|------|----------|--------|--------------|
| [`bash-rate-limiter`](#bash-rate-limiter) | ERROR | PreToolUse | Circuit-breaks after N destructive commands within a time window |
| [`cloud-infra-mutation`](#cloud-infra-mutation) | ERROR | PreToolUse | Blocks NAT, firewall, VPC, IAM, and load balancer mutations across AWS/GCP/Azure |
| [`cloud-paid-resource-creation`](#cloud-paid-resource-creation) | WARNING | PreToolUse | Warns when creating paid cloud resources (VMs, IPs, DBs, clusters) |
| [`cloud-resource-deletion`](#cloud-resource-deletion) | ERROR | PreToolUse | Blocks AWS/GCP/Azure resource deletion without session confirmation |
| [`cross-account-guard`](#cross-account-guard) | WARNING | PreToolUse | Warns on cloud account/project switches within the same session |
| [`destructive-confirmation-gate`](#destructive-confirmation-gate) | ERROR | PreToolUse | Blocks DROP DATABASE, terraform destroy, kubectl delete namespace without confirmation |
| [`docker-volume-guard`](#docker-volume-guard) | WARNING | PreToolUse | Blocks privileged Docker containers; warns on volume deletion and force-remove |
| [`dry-run-required`](#dry-run-required) | ERROR | PreToolUse | Requires --dry-run/--check for terraform, kubectl, ansible, helm before apply |
| [`network-firewall-guard`](#network-firewall-guard) | ERROR | PreToolUse | Blocks iptables flush, ufw disable, firewalld permanent rules, and default route changes |
| [`operation-journal`](#operation-journal) | INFO | PostToolUse, Stop | Records all tool operations to an audit log, emits summary at Stop |
| [`package-manager-in-chroot`](#package-manager-in-chroot) | WARNING | PreToolUse | Warns on apt, dpkg, yum, dnf, or pacman invocations inside a chroot |
| [`production-guard`](#production-guard) | ERROR | PreToolUse | Blocks commands targeting production environments (DB, gcloud, AWS) |
| [`remote-boot-partition-guard`](#remote-boot-partition-guard) | ERROR | PreToolUse | Blocks rm or dd targeting boot-critical paths (/boot/vmlinuz, /boot/initrd, /boot/grub) |
| [`remote-chroot-guard`](#remote-chroot-guard) | WARNING | PreToolUse | Blocks bootloader removal in chroot; warns on risky repair commands in chroot |
| [`ssh-destructive-command-guard`](#ssh-destructive-command-guard) | WARNING | PreToolUse | Detects destructive commands (rm -rf, mkfs, reboot, etc.) run via SSH |
| [`subagent-safety-briefing`](#subagent-safety-briefing) | INFO | SubagentStart | Injects safety notice into subagent context on spawn |
| [`subagent-transcript-audit`](#subagent-transcript-audit) | WARNING | SubagentStop | Audits subagent transcripts for dangerous commands post-execution |
| [`system-scheduler-guard`](#system-scheduler-guard) | WARNING | PreToolUse | Warns on crontab, systemctl enable/disable, launchctl, and scheduler file writes |
<!-- END GENERATED: pack-autopilot -->

Claude Code subagents do not trigger the parent session's hooks; the autopilot pack's `subagent-safety-briefing` and `subagent-transcript-audit` rules partly compensate. See [Subagent safety](subagent-safety.md).

### `bash-rate-limiter`

Circuit-breaks after N destructive commands within a time window. Prevents runaway automation.

**Config options:**
- `max_destructive_ops` — Maximum destructive operations before blocking (default: `5`)
- `window_seconds` — Time window in seconds (default: `300`)

### `cloud-infra-mutation`

Blocks NAT, firewall, VPC, IAM, and load balancer mutations across AWS/GCP/Azure.

**Config options:**
- `allowed_ops` — List of allowed mutation operations (bypass guard)

### `cloud-paid-resource-creation`

Warns when creating paid cloud resources (VMs, IPs, databases, clusters).

**Config options:**
- `suppress_warnings` — List of resource types to suppress warnings for

### `cloud-resource-deletion`

Blocks AWS/GCP/Azure resource deletion commands unless a session-level confirmation key has been set.

**Config options:**
- `allowed_ops` — List of allowed deletion operations (bypass guard)

### `cross-account-guard`

Warns on cloud account/project switches within the same session (e.g., `gcloud config set project`, `aws sts assume-role`).

### `destructive-confirmation-gate`

Blocks `DROP DATABASE`, `terraform destroy`, and `kubectl delete namespace` unless a session-level confirmation key has been set via `session_state`.

### `docker-volume-guard`

*PreToolUse, WARNING/ERROR*

Blocks privileged Docker containers (ERROR); warns on volume deletion and force-remove (WARNING).

**Config options:**
- `allowed_ops` — List of allowed Docker operations (bypass guard)

### `dry-run-required`

Requires `--dry-run` or `--check` flags for terraform, kubectl, ansible, and helm apply/install/upgrade commands.

**Config options:**
- `bypass_tools` — List of tools that bypass the dry-run requirement

### `network-firewall-guard`

Blocks iptables flush, ufw disable, firewalld permanent rules, and default route changes.

**Config options:**
- `allowed_ops` — List of allowed firewall operations (bypass guard)

### `operation-journal`

Records all tool operations to an in-memory audit log. Emits a summary at session end.

### `package-manager-in-chroot`

Warns on `apt`/`dpkg`/`yum`/`dnf`/`pacman` usage inside chroot environments.

### `production-guard`

Blocks commands targeting production environments (database connections, cloud CLI with production project/host patterns).

**Config options:**
- `allowed_projects` — Cloud project names that are allowed (bypass guard)
- `allowed_hosts` — Database hostnames that are allowed

### `remote-boot-partition-guard`

Blocks `rm` or `dd` targeting `/boot` kernel and bootloader files via SSH.

### `remote-chroot-guard`

*PreToolUse, WARNING/ERROR*

Detects bootloader package removal and risky repair commands inside chroot environments. ERROR for bootloader removal, WARNING for risky repair.

### `ssh-destructive-command-guard`

*PreToolUse, WARNING/ERROR*

Detects destructive commands via SSH: `rm -rf`, `mkfs`, `dd`, `reboot`, `iptables flush`, `terraform destroy`. ERROR for catastrophic patterns, WARNING for risky ones.

### `subagent-safety-briefing`

Injects a safety notice into subagent context on spawn. Tracks spawned subagents in `session_state`.

### `subagent-transcript-audit`

Audits subagent JSONL transcripts for dangerous commands (rm -rf, terraform destroy, cloud deletions, etc.) after execution. Records audit results in `session_state` for the session report.

### `system-scheduler-guard`

Warns on crontab edits, systemctl enable/disable, launchctl load/unload, and scheduler file writes.
