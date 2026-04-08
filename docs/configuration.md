# Configuration Reference

AgentLint is configured via `agentlint.yml` (or `agentlint.yaml`, `.agentlint.yml`) in your project root. Run `agentlint init` to generate one with auto-detected defaults.

## Quick reference

```yaml
# All options with their defaults
stack: auto                    # auto | manual
severity: standard             # strict | standard | relaxed
packs:
  - universal                  # Always active (18 rules)
  # - python                   # Auto-detected from pyproject.toml / setup.py
  # - frontend                 # Auto-detected from package.json
  # - react                    # Auto-detected from react in dependencies
  # - seo                      # Auto-detected from SSR/SSG framework
  # - security                 # Opt-in: blocks Bash file writes, network exfiltration
  # - autopilot                # Opt-in: guards for unattended/autonomous sessions
  # - mypack                   # Custom packs: name matches pack attribute in custom rules
# custom_rules_dir: .agentlint/rules/   # Path to custom rule files

rules:
  # === Universal pack ===
  no-secrets:        { enabled: true }                  # ERROR - blocks secrets in writes
  no-env-commit:     { enabled: true }                  # ERROR - blocks .env file writes
  no-force-push:     { enabled: true }                  # ERROR - blocks force-push to main
  no-destructive-commands: { enabled: true }             # WARNING - warns on rm -rf, DROP TABLE
  dependency-hygiene: { enabled: true }                  # WARNING - warns on ad-hoc pip/npm install
  max-file-size:     { enabled: true, limit: 500 }      # WARNING - warns on large files
  drift-detector:    { enabled: true, threshold: 10 }    # WARNING - warns on many edits without tests
  no-debug-artifacts: { enabled: true }                  # WARNING - detects leftover debug statements
  test-with-changes: { enabled: true }                   # WARNING - warns if no tests updated
  no-todo-left:      { enabled: true }                   # INFO - reports TODO/FIXME in changed files
  no-push-to-main:   { enabled: true }                   # WARNING - warns on direct push to main/master
  no-skip-hooks:     { enabled: true }                   # WARNING - warns on git commit --no-verify
  no-test-weakening: { enabled: true }                   # WARNING - warns on skipped tests, assert True
  git-checkpoint:    { enabled: false }                  # INFO - creates git stash before destructive ops (opt-in)
  cicd-pipeline-guard: { enabled: true }            # ERROR - blocks CI/CD pipeline changes without approval
  package-publish-guard: { enabled: true }           # ERROR - blocks npm publish, twine upload, gem push
  cli-integration: {}                                 # Run external CLI tools on PostToolUse (see below)
  # === Quality pack (always-active) ===
  commit-message-format: { enabled: true }               # WARNING - validates conventional commits
  no-error-handling-removal: { enabled: true }            # WARNING - warns when error handling removed
  no-large-diff:     { max_lines_added: 200, max_lines_removed: 100 }  # WARNING - large edit detection
  no-file-creation-sprawl: { max_new_files: 10 }         # WARNING - file sprawl detection
  naming-conventions: { enabled: true }                   # INFO - file naming conventions
  no-dead-imports:   { enabled: true }                   # INFO - detects unused imports
  self-review-prompt: { enabled: true }                  # INFO - adversarial self-review at session end
  # === Security pack (opt-in) ===
  # no-bash-file-write: { enabled: true }                # ERROR - blocks Bash file writes (cat >, tee, etc.)
  # no-network-exfil:   { enabled: true }                # ERROR - blocks potential data exfiltration
  # === Python pack ===
  # no-bare-except:    { enabled: true, allow_reraise: true }
  # no-unsafe-shell:   { enabled: true }
  # no-sql-injection:  { enabled: true }
  # === Frontend pack ===
  # a11y-image-alt:    { enabled: true }
  # mobile-touch-targets: { enabled: true }
  # === React pack ===
  # react-query-loading-state: { enabled: true }
  # === SEO pack ===
  # seo-page-metadata: { enabled: true }
```

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

Built-in packs: `universal`, `quality`, `python`, `frontend`, `react`, `seo`, `security`, `autopilot`.

Custom packs are also supported — add any pack name to `packs:` and set `custom_rules_dir`. Rules whose `pack` attribute matches the name will activate.

```yaml
packs:
  - universal
  - python
  - frontend
  - fintech          # custom pack — rules in custom_rules_dir with pack = "fintech"
```

Use `agentlint doctor` to detect orphaned packs (custom rules whose pack isn't in `packs:`).

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

### `no-env-commit` (PreToolUse, ERROR)

Blocks writing `.env`, `.env.local`, `.env.production`, and similar credential files. Also detects Bash commands that write to `.env` files (e.g. `echo "SECRET=val" > .env`, `cp .env.example .env`, `tee .env`, `sed -i ... .env`).

### `no-force-push` (PreToolUse, ERROR)

Blocks `git push --force` or `git push -f` to `main` or `master` branches.

### `no-destructive-commands` (PreToolUse, WARNING/ERROR)

Warns on destructive shell commands. Some patterns escalate to ERROR severity:

**WARNING:**
- `rm -rf` (except safe targets like `node_modules`, `dist`, `__pycache__`)
- `DROP TABLE`, `DROP DATABASE`
- `git reset --hard`, `git clean -fd`
- `chmod 777` (overly permissive)
- `docker system prune -a --volumes`
- `kubectl delete namespace`

**ERROR (catastrophic):**
- `rm -rf /` or `rm -rf ~` (root/home deletion)
- `mkfs` (filesystem format)
- `dd if=/dev/zero` (disk wipe)
- Fork bombs
- `git branch -D main/master` (protected branch deletion)

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

### `no-push-to-main` (PreToolUse, WARNING)

Warns on direct `git push` to `main` or `master` branches (excluding force pushes, which are handled by `no-force-push`).

### `no-skip-hooks` (PreToolUse, WARNING)

Warns when git commands use `--no-verify` or `--no-gpg-sign` flags to skip safety hooks.

### `no-test-weakening` (PreToolUse, WARNING)

Detects patterns that weaken test suites when writing to test files:
- Skip markers (`@pytest.mark.skip`, `@unittest.skip`, `it.skip()`, `describe.skip()`)
- Trivially passing assertions (`assert True`, `assertTrue(True)`, `expect(true).toBe(true)`)
- Commented-out assertions (`# assert ...`, `// expect(...)`)
- `@pytest.mark.xfail` without a reason
- Empty test functions (`def test_...: pass`)

### `git-checkpoint` (PreToolUse + Stop, INFO) — disabled by default

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

### `token-budget` (PostToolUse + Stop, WARNING/INFO)

Tracks session activity (tool invocations, content bytes, duration). Warns at configurable threshold.

**Config options:**
- `max_tool_invocations` — Maximum tool calls before warning (default: `200`)
- `max_content_bytes` — Maximum content bytes (default: `500000`)
- `warn_at_percent` — Warning threshold (default: `80`)

### `file-scope` (PreToolUse, ERROR)

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

### `cicd-pipeline-guard` (PreToolUse, ERROR)

Blocks modifications to CI/CD pipeline files (`.github/workflows/`, `.gitlab-ci.yml`, `Jenkinsfile`, etc.) without a session-level confirmation key. Prevents accidental pipeline changes during autonomous sessions.

### `package-publish-guard` (PreToolUse, ERROR)

Blocks package publish commands: `npm publish`, `twine upload`, `gem push`, `cargo publish`. Prevents accidental releases during automated sessions.

### `cli-integration` (PostToolUse, configurable)

Runs external CLI tools on file changes and reports non-zero exit codes as violations. Configure commands with template placeholders:

```yaml
rules:
  cli-integration:
    commands:
      - name: ruff
        on: ["Write", "Edit"]        # Tool filter (default: Write, Edit)
        glob: "**/*.py"              # File filter (default: **/*)
        command: "ruff check {file.path} --output-format=concise"
        timeout: 10                  # Seconds (default: 10)
        severity: warning            # error | warning | info (default: warning)

      - name: pip-audit
        on: ["Write", "Edit"]
        glob: "**/requirements*.txt"
        command: "pip-audit -r {file.path}"
        timeout: 30
        severity: warning

      - name: pytest-related
        on: ["Write", "Edit"]
        glob: "src/**/*.py"
        command: "pytest tests/ -k {file.stem} -x -q --tb=short"
        timeout: 60
        severity: info
```

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

## CI Mode

`agentlint ci` scans changed files and reports violations for CI pipelines:

```bash
agentlint ci                              # scan uncommitted changes
agentlint ci --diff origin/main...HEAD    # scan PR diff
agentlint ci --format json                # machine-readable output
```

**Options:**
- `--diff <range>` — Git diff range (e.g., `origin/main...HEAD`). If omitted, scans staged + unstaged + untracked files.
- `--project-dir <path>` — Project directory (default: current directory)
- `--format text|json` — Output format (default: `text`)

**Exit codes:**
- `0` — Clean, or only WARNING/INFO violations
- `1` — ERROR violations found

**GitHub Actions example:**

```yaml
name: AgentLint
on: [pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: pip install agentlint
      - run: agentlint ci --diff origin/${{ github.base_ref }}...HEAD
```

Binary files are automatically skipped. The same `agentlint.yml` config (packs, rules, severity) applies.

## AGENTS.md Integration

AgentLint can import conventions from your project's [AGENTS.md](https://agents.md/) file — the industry standard for AI agent instructions.

### `agentlint import-agents-md`

```bash
# Preview what would be generated
agentlint import-agents-md --dry-run

# Generate agentlint.yml from AGENTS.md
agentlint import-agents-md

# Merge AGENTS.md conventions into existing config
agentlint import-agents-md --merge

# Specify project directory
agentlint import-agents-md --project-dir /path/to/project
```

**How mapping works:**
- Section headings and body text are scanned for keywords
- Keywords map to packs: "Python" / "pytest" -> python pack, "React" / "JSX" -> react pack, etc.
- Keywords map to rules: ".env" -> no-env-commit, "commit message" -> commit-message-format, etc.
- Inferred rules use INFO severity (conservative defaults)

**Auto-detection integration:**
When `AGENTS.md` exists and `stack: auto` is set, AgentLint uses AGENTS.md hints to discover additional packs during stack detection. This is additive — existing detection logic is not affected.

## Security rules reference

The security pack is **opt-in** — add `security` to your `packs` list to enable it. These rules provide stricter enforcement for sensitive environments.

### `no-bash-file-write` (PreToolUse, ERROR)

Blocks file writes via Bash commands, enforcing use of the Write/Edit tools instead. Detects: `cat >`, `echo >`, `tee`, `sed -i`, `cp`, `mv`, `perl -pi`, `awk >`, `dd of=`, `python -c ... open(...).write()`, and heredocs.

**Config options:**
- `allow_paths` — Glob patterns for allowed write targets (e.g. `["*.log", "/tmp/*"]`)
- `allow_patterns` — Regex patterns for allowed commands (e.g. `["echo.*>>.*\\.log"]`)

### `no-network-exfil` (PreToolUse, ERROR)

Blocks potential data exfiltration via network commands. Detects: `curl POST/PUT` with data, `curl -d @file`, piping secrets to curl, `nc` with sensitive files, `scp` of credential files, `wget --post-file`, `python requests.post()`, and `rsync` of sensitive files to remote.

Default allowed hosts: `github.com`, `pypi.org`, `registry.npmjs.org`, `rubygems.org`.

**Config options:**
- `allowed_hosts` — Additional allowed destination hosts

### `env-credential-reference` (PreToolUse, WARNING)

Warns when environment variable patterns reference local file paths (e.g., `DATABASE_URL_FILE=/etc/secrets/db`), which may indicate credential leakage risk.

## Python rules reference

### `no-bare-except` (PreToolUse, WARNING)

Prevents bare `except:` clauses that catch all exceptions including `SystemExit` and `KeyboardInterrupt`.

**Config options:**
- `allow_reraise` — Allow bare except if it contains a bare `raise` (default: `true`)

### `no-unsafe-shell` (PreToolUse, ERROR)

Blocks unsafe shell execution via `subprocess` with `shell=True` and `os` module shell functions.

**Config options:**
- `allow_shell_true` — Allow subprocess calls with `shell=True` (default: `false`)

### `no-dangerous-migration` (PreToolUse, WARNING)

Warns about dangerous database migration operations in Alembic migration files (dropping columns, renaming tables, etc.).

**Config options:**
- `migration_paths` — Custom path markers for migration files (default: detects `migration`, `alembic`, `versions` in path)
- `require_timezone` — Enforce `timezone=True` on DateTime columns (default: `true`)

### `no-wildcard-import` (PreToolUse, WARNING)

Prevents `from module import *` which pollutes the namespace and makes dependencies unclear.

**Config options:**
- `allow_in` — Files where wildcard imports are allowed (default: `["__init__.py"]`)

### `no-unnecessary-async` (PostToolUse, INFO)

Flags `async def` functions that never use `await`. Skips test files and stub/abstract implementations.

**Config options:**
- `ignore_decorators` — Additional decorator names to skip (default: merges with `property`, `override`, `abstractmethod`)

### `no-sql-injection` (PreToolUse, ERROR)

Blocks SQL queries built via string interpolation (f-strings, `.format()`, `%` operator, concatenation).

**Config options:**
- `extra_keywords` — Additional SQL keywords to detect beyond `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`

## Frontend rules reference

### `a11y-image-alt` (PreToolUse, WARNING)

Ensures images have `alt` text for screen readers (WCAG 1.1.1).

**Config options:**
- `extra_components` — Additional image component names beyond `img` and `Image`

### `a11y-form-labels` (PreToolUse, WARNING)

Ensures form inputs have associated `<label>` elements or `aria-label` attributes (WCAG 1.3.1).

### `a11y-interactive-elements` (PreToolUse, WARNING)

Ensures interactive elements have proper ARIA attributes. Detects link anti-patterns like "click here".

**Config options:**
- `link_anti_patterns` — Custom anti-pattern phrases (default: `click here`, `read more`, `learn more`, `here`)

### `a11y-heading-hierarchy` (PreToolUse, INFO)

Ensures proper heading hierarchy — no multiple `<h1>` elements and no skipped heading levels.

**Config options:**
- `max_h1` — Maximum number of `<h1>` elements per page (default: `1`)

### `mobile-touch-targets` (PreToolUse, WARNING)

Ensures interactive elements meet minimum touch target size of 44x44 CSS pixels (WCAG 2.5.5).

### `mobile-responsive-patterns` (PreToolUse, INFO)

Warns about desktop-only layout patterns: large grids without responsive breakpoints, fixed widths, and hover-only interactions.

**Config options:**
- `min_grid_cols_warning` — Minimum grid columns that trigger a warning (default: `4`)

### `style-no-arbitrary-values` (PreToolUse, INFO)

Warns about arbitrary Tailwind CSS values (e.g. `w-[347px]`, `text-[#1a2b3c]`) that bypass design tokens.

### `style-focus-visible` (PreToolUse, WARNING)

Ensures focus indicators (`outline`, `ring`) are not removed without replacement. Checks for `outline: none` or `outline-none` without a `focus-visible` or `focus:ring` alternative (WCAG 2.4.7).

## React rules reference

### `react-query-loading-state` (PreToolUse, WARNING)

Ensures `useQuery` / `useSuspenseQuery` results destructure and handle `isLoading` and `isError` (or `error`) states.

**Config options:**
- `hooks` — Custom query hook names (default: `useQuery`, `useSuspenseQuery`)

### `react-empty-state` (PreToolUse, INFO)

Suggests adding empty state handling when `array.map()` is used in JSX without a corresponding length/empty check.

### `react-lazy-loading` (PreToolUse, INFO)

Suggests `React.lazy()` for heavy components imported in page-level files. Ensures `<Suspense>` wraps lazy-loaded components.

**Config options:**
- `heavy_components` — Custom component names considered heavy (default: `Chart`, `DataTable`, `Editor`, `Calendar`, `Map`, `RichTextEditor`, `CodeEditor`, `Spreadsheet`)
- `page_patterns` — Custom path patterns for page files (default: `pages/`, `app/`, `routes/`)

## SEO rules reference

### `seo-page-metadata` (PreToolUse, WARNING)

Ensures page files include `<title>` and meta description. Detects framework-specific patterns (Next.js `generateMetadata`, Nuxt `useHead`, etc.).

**Config options:**
- `page_patterns` — Custom page path patterns (default: `pages/`, `app/`, `routes/`)
- `metadata_components` — Additional metadata component names

### `seo-open-graph` (PreToolUse, INFO)

Ensures pages that have metadata also include Open Graph (`og:`) tags for social media previews.

**Config options:**
- `required_properties` — Required OG properties (default: `og:title`, `og:description`, `og:image`)

### `seo-semantic-html` (PreToolUse, INFO)

Encourages semantic HTML elements (`<main>`, `<nav>`, `<article>`, `<section>`) over excessive `<div>` usage.

**Config options:**
- `min_div_threshold` — Minimum number of `<div>` elements before warning (default: `10`)

### `seo-structured-data` (PreToolUse, INFO)

Suggests adding JSON-LD structured data (`<script type="application/ld+json">`) to content pages.

**Config options:**
- `content_path_patterns` — Path patterns for content pages (default: `product`, `article`, `blog`, `post`, `recipe`, `event`)

## Autopilot rules reference

The autopilot pack is designed for **unattended / autonomous agent sessions** — it guards against infrastructure-level damage, enforces confirmation gates, and audits subagent activity. Add `autopilot` to your `packs` list to enable it.

### `production-guard` (PreToolUse, ERROR)

Blocks commands targeting production environments (database connections, cloud CLI with production project/host patterns).

**Config options:**
- `allowed_projects` — Cloud project names that are allowed (bypass guard)
- `allowed_hosts` — Database hostnames that are allowed

### `destructive-confirmation-gate` (PreToolUse, ERROR)

Blocks `DROP DATABASE`, `terraform destroy`, and `kubectl delete namespace` unless a session-level confirmation key has been set via `session_state`.

### `cloud-resource-deletion` (PreToolUse, ERROR)

Blocks AWS/GCP/Azure resource deletion commands unless a session-level confirmation key has been set.

**Config options:**
- `allowed_ops` — List of allowed deletion operations (bypass guard)

### `cloud-infra-mutation` (PreToolUse, ERROR)

Blocks NAT, firewall, VPC, IAM, and load balancer mutations across AWS/GCP/Azure.

**Config options:**
- `allowed_ops` — List of allowed mutation operations (bypass guard)

### `cloud-paid-resource-creation` (PreToolUse, WARNING)

Warns when creating paid cloud resources (VMs, IPs, databases, clusters).

**Config options:**
- `suppress_warnings` — List of resource types to suppress warnings for

### `dry-run-required` (PreToolUse, ERROR)

Requires `--dry-run` or `--check` flags for terraform, kubectl, ansible, and helm apply/install/upgrade commands.

**Config options:**
- `bypass_tools` — List of tools that bypass the dry-run requirement

### `bash-rate-limiter` (PreToolUse, ERROR)

Circuit-breaks after N destructive commands within a time window. Prevents runaway automation.

**Config options:**
- `max_destructive_ops` — Maximum destructive operations before blocking (default: `5`)
- `window_seconds` — Time window in seconds (default: `300`)

### `cross-account-guard` (PreToolUse, WARNING)

Warns on cloud account/project switches within the same session (e.g., `gcloud config set project`, `aws sts assume-role`).

### `network-firewall-guard` (PreToolUse, ERROR)

Blocks iptables flush, ufw disable, firewalld permanent rules, and default route changes.

**Config options:**
- `allowed_ops` — List of allowed firewall operations (bypass guard)

### `docker-volume-guard` (PreToolUse, WARNING/ERROR)

Blocks privileged Docker containers (ERROR); warns on volume deletion and force-remove (WARNING).

**Config options:**
- `allowed_ops` — List of allowed Docker operations (bypass guard)

### `system-scheduler-guard` (PreToolUse, WARNING)

Warns on crontab edits, systemctl enable/disable, launchctl load/unload, and scheduler file writes.

### `operation-journal` (PostToolUse + Stop, INFO)

Records all tool operations to an in-memory audit log. Emits a summary at session end.

### `subagent-safety-briefing` (SubagentStart, INFO)

Injects a safety notice into subagent context on spawn. Tracks spawned subagents in `session_state`.

### `subagent-transcript-audit` (SubagentStop, WARNING)

Audits subagent JSONL transcripts for dangerous commands (rm -rf, terraform destroy, cloud deletions, etc.) after execution. Records audit results in `session_state` for the session report.

### `ssh-destructive-command-guard` (PreToolUse, WARNING/ERROR)

Detects destructive commands via SSH: `rm -rf`, `mkfs`, `dd`, `reboot`, `iptables flush`, `terraform destroy`. ERROR for catastrophic patterns, WARNING for risky ones.

### `remote-boot-partition-guard` (PreToolUse, ERROR)

Blocks `rm` or `dd` targeting `/boot` kernel and bootloader files via SSH.

### `remote-chroot-guard` (PreToolUse, WARNING/ERROR)

Detects bootloader package removal and risky repair commands inside chroot environments. ERROR for bootloader removal, WARNING for risky repair.

### `package-manager-in-chroot` (PreToolUse, WARNING)

Warns on `apt`/`dpkg`/`yum`/`dnf`/`pacman` usage inside chroot environments.

## Full example

```yaml
stack: auto
severity: standard

packs:
  - universal
  # - python
  # - frontend
  # - react
  # - seo
  # - security          # Opt-in: blocks Bash file writes, network exfiltration
  # - autopilot         # Opt-in: guards for unattended/autonomous sessions

rules:
  # Universal
  no-secrets:
    enabled: true
    extra_prefixes: []        # Additional token prefixes to detect
  no-env-commit:
    enabled: true
  no-force-push:
    enabled: true
  no-push-to-main:
    enabled: true
  no-skip-hooks:
    enabled: true
  no-test-weakening:
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
  git-checkpoint:
    enabled: false            # Opt-in: creates git stash before destructive ops
    cleanup_hours: 24
  token-budget:
    max_tool_invocations: 200
    warn_at_percent: 80

  # Quality (always-active)
  commit-message-format:
    enabled: true
  no-dead-imports:
    enabled: true
  no-error-handling-removal:
    enabled: true
  self-review-prompt:
    enabled: true

  # Security (opt-in)
  no-bash-file-write:
    allow_paths: []           # Glob patterns for allowed targets
    allow_patterns: []        # Regex patterns for allowed commands
  no-network-exfil:
    allowed_hosts: []         # Additional allowed hosts

  # Python
  no-bare-except:
    allow_reraise: true
  no-unsafe-shell:
    allow_shell_true: false
  no-dangerous-migration:
    require_timezone: true
  no-wildcard-import:
    allow_in: ["__init__.py"]
  no-sql-injection:
    enabled: true

  # Frontend
  a11y-image-alt:
    enabled: true
  a11y-heading-hierarchy:
    max_h1: 1
  mobile-responsive-patterns:
    min_grid_cols_warning: 4

  # React
  react-query-loading-state:
    enabled: true
  react-lazy-loading:
    heavy_components: ["Chart", "DataTable", "Editor"]

  # SEO
  seo-page-metadata:
    enabled: true
  seo-semantic-html:
    min_div_threshold: 10
  seo-structured-data:
    content_path_patterns: ["product", "article", "blog"]

  # CLI integration — run external tools on PostToolUse
  # cli-integration:
  #   commands:
  #     - name: ruff
  #       on: ["Write", "Edit"]
  #       glob: "**/*.py"
  #       command: "ruff check {file.path} --output-format=concise"
  #       timeout: 10
  #       severity: warning

  # Autopilot (opt-in)
  production-guard:
    allowed_projects: []      # Cloud projects to allow
    allowed_hosts: []         # DB hostnames to allow
  bash-rate-limiter:
    max_destructive_ops: 5
    window_seconds: 300
  dry-run-required:
    bypass_tools: []          # Tools that skip dry-run requirement
  cloud-resource-deletion:
    allowed_ops: []
  cloud-infra-mutation:
    allowed_ops: []
  cloud-paid-resource-creation:
    suppress_warnings: []
  network-firewall-guard:
    allowed_ops: []
  docker-volume-guard:
    allowed_ops: []

# custom_rules_dir: .agentlint/rules/
# Custom rules with pack = "mypack" activate when "mypack" is in packs above
```
