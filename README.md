# agentlint

[![CI](https://github.com/mauhpr/agentlint/actions/workflows/ci.yml/badge.svg)](https://github.com/mauhpr/agentlint/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/mauhpr/agentlint/branch/main/graph/badge.svg)](https://codecov.io/gh/mauhpr/agentlint)
[![PyPI](https://img.shields.io/pypi/v/agentlint)](https://pypi.org/project/agentlint/)
[![Python](https://img.shields.io/pypi/pyversions/agentlint)](https://pypi.org/project/agentlint/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Real-time guardrails for AI coding agents — code quality, security, and infrastructure safety.

AI coding agents drift during long sessions — they introduce API keys into source, skip tests, force-push to main, and leave debug statements behind. AgentLint catches these problems *as they happen*, not at review time.

## Vision

The short-term problem is code quality: secrets, broken tests, force-pushes, debug artifacts. AgentLint solves that today with 68 rules that run locally in milliseconds.

The longer-term question is harder: **what does it mean for an agent to operate safely on real infrastructure?** When an agent can run `gcloud`, `kubectl`, `terraform`, or `iptables`, the blast radius is no longer a bad commit — it's a production outage or a deleted database.

We don't have a mature answer to that yet. Nobody does. The **autopilot pack** is our first experiment in that direction — explicit, opt-in, and clearly labeled as such. The goal is to start building the intuition and tooling for autonomous agent safety at the infrastructure level, and to do it in the open.

## What it catches

AgentLint ships with 68 rules across 8 packs, covering all 17 Claude Code hook events. The 19 **universal** rules and 7 **quality** rules work with any tech stack; 4 additional packs auto-activate based on your project files; the **security** pack is opt-in; and the **autopilot** pack is opt-in and experimental:

| Rule | Severity | What it does |
|------|----------|-------------|
| `no-secrets` | ERROR | Blocks writes containing API keys, tokens, passwords, private keys, JWTs |
| `no-env-commit` | ERROR | Blocks writing `.env` files (including via Bash) |
| `no-force-push` | ERROR | Blocks `git push --force` to main/master |
| `no-push-to-main` | WARNING | Warns on direct push to main/master |
| `no-skip-hooks` | WARNING | Warns on `git commit --no-verify` |
| `no-destructive-commands` | WARNING | Warns on `rm -rf`, `DROP TABLE`, `chmod 777`, `mkfs`, and more |
| `no-test-weakening` | WARNING | Detects skipped tests, `assert True`, commented-out assertions |
| `dependency-hygiene` | WARNING | Warns on ad-hoc `pip install` / `npm install` |
| `max-file-size` | WARNING | Warns when a file exceeds 500 lines |
| `drift-detector` | WARNING | Warns after many edits without running tests |
| `no-debug-artifacts` | WARNING | Detects `console.log`, `print()`, `debugger` left in code |
| `test-with-changes` | WARNING | Warns if source changed but no tests were updated |
| `token-budget` | WARNING | Tracks session activity and warns on excessive tool usage |
| `git-checkpoint` | INFO | Creates git stash before destructive ops (opt-in, disabled by default) |
| `no-todo-left` | INFO | Reports TODO/FIXME comments in changed files |

**ERROR** rules block the agent's action. **WARNING** rules inject advice into the agent's context. **INFO** rules appear in the session report.

<details>
<summary><strong>Quality pack</strong> (7 rules) — always active alongside universal</summary>

| Rule | Severity | What it does |
|------|----------|-------------|
| `commit-message-format` | WARNING | Validates commit messages follow conventional format |
| `no-error-handling-removal` | WARNING | Warns when try/except or .catch() blocks are removed |
| `no-large-diff` | WARNING | Warns when a single edit adds >200 or removes >100 lines |
| `no-file-creation-sprawl` | WARNING | Warns when >10 new files created in a session |
| `naming-conventions` | INFO | Checks file names match language conventions (snake_case, camelCase, PascalCase) |
| `no-dead-imports` | INFO | Detects unused imports in Python and JS/TS files |
| `self-review-prompt` | INFO | Injects adversarial self-review prompt at session end |

</details>

<details>
<summary><strong>Python pack</strong> (6 rules) — auto-activates when <code>pyproject.toml</code> or <code>setup.py</code> exists</summary>

| Rule | Severity | What it does |
|------|----------|-------------|
| `no-bare-except` | WARNING | Prevents bare `except:` clauses that swallow all exceptions |
| `no-unsafe-shell` | ERROR | Blocks unsafe shell execution via subprocess or os module |
| `no-dangerous-migration` | WARNING | Warns on risky Alembic migration operations |
| `no-wildcard-import` | WARNING | Prevents `from module import *` |
| `no-unnecessary-async` | INFO | Flags async functions that never use `await` |
| `no-sql-injection` | ERROR | Blocks SQL via string interpolation (f-strings, `.format()`) |

</details>

<details>
<summary><strong>Frontend pack</strong> (8 rules) — auto-activates when <code>package.json</code> exists</summary>

| Rule | Severity | What it does |
|------|----------|-------------|
| `a11y-image-alt` | WARNING | Ensures images have alt text (WCAG 1.1.1) |
| `a11y-form-labels` | WARNING | Ensures form inputs have labels or `aria-label` |
| `a11y-interactive-elements` | WARNING | Checks ARIA attributes and link anti-patterns |
| `a11y-heading-hierarchy` | INFO | Ensures no skipped heading levels or multiple h1s |
| `mobile-touch-targets` | WARNING | Ensures 44x44px minimum touch targets (WCAG 2.5.5) |
| `mobile-responsive-patterns` | INFO | Warns about desktop-only layout patterns |
| `style-no-arbitrary-values` | INFO | Warns about arbitrary Tailwind values bypassing tokens |
| `style-focus-visible` | WARNING | Ensures focus indicators are not removed (WCAG 2.4.7) |

</details>

<details>
<summary><strong>React pack</strong> (3 rules) — auto-activates when <code>react</code> is in <code>package.json</code> dependencies</summary>

| Rule | Severity | What it does |
|------|----------|-------------|
| `react-query-loading-state` | WARNING | Ensures `useQuery` results handle loading and error states |
| `react-empty-state` | INFO | Suggests empty state handling for `array.map()` in JSX |
| `react-lazy-loading` | INFO | Suggests lazy loading for heavy components in page files |

</details>

<details>
<summary><strong>SEO pack</strong> (4 rules) — auto-activates when an SSR/SSG framework (Next.js, Nuxt, Gatsby, Astro, etc.) is detected</summary>

| Rule | Severity | What it does |
|------|----------|-------------|
| `seo-page-metadata` | WARNING | Ensures page files include title and description |
| `seo-open-graph` | INFO | Ensures pages with metadata include Open Graph tags |
| `seo-semantic-html` | INFO | Encourages semantic HTML over excessive divs |
| `seo-structured-data` | INFO | Suggests JSON-LD structured data for content pages |

</details>

<details>
<summary><strong>Security pack</strong> (3 rules) — opt-in, add <code>security</code> to your packs list</summary>

| Rule | Severity | What it does |
|------|----------|-------------|
| `no-bash-file-write` | ERROR | Blocks file writes via Bash (`cat >`, `tee`, `sed -i`, `cp`, heredocs, etc.) |
| `no-network-exfil` | ERROR | Blocks data exfiltration via `curl POST`, `nc`, `scp`, `wget --post-file` |
| `env-credential-reference` | WARNING | Warns when `*_FILE` env vars reference local paths (credential leakage risk) |

The security pack addresses the most common agent escape hatch: bypassing Write/Edit guardrails via the Bash tool. Enable it by adding `security` to your packs list:

```yaml
packs:
  - universal
  - security  # Blocks Bash file writes and network exfiltration
```

Configure allowlists for legitimate use cases:

```yaml
rules:
  no-bash-file-write:
    allow_patterns: ["echo.*>>.*\\.log"]  # Allow appending to logs
    allow_paths: ["*.log", "/tmp/*"]       # Allow writes to temp/log
  no-network-exfil:
    allowed_hosts: ["internal.corp.com"]   # Allow specific hosts
```

</details>

<details>
<summary><strong>Autopilot pack</strong> (18 rules) — ⚠️ experimental, opt-in</summary>

> **Alpha quality.** The autopilot pack is an early experiment in agent safety guardrails for cloud and infrastructure operations. Regex-based heuristics will produce false positives and false negatives — a mature framework for this problem doesn't exist yet. Enable it, experiment with it, report what breaks. Use at your own risk in production environments.

| Rule | Severity | What it does |
|------|----------|-------------|
| `production-guard` | ERROR | Blocks Bash commands targeting production databases, gcloud projects, or AWS accounts |
| `destructive-confirmation-gate` | ERROR | Blocks DROP DATABASE, terraform destroy, kubectl delete namespace, etc. without explicit acknowledgment |
| `dry-run-required` | WARNING | Requires --dry-run/--check/plan preview before terraform apply, kubectl apply, ansible-playbook, helm upgrade/install, and pulumi up |
| `bash-rate-limiter` | WARNING | Circuit-breaks after N destructive commands within a time window (default: 5 ops / 300s) |
| `cross-account-guard` | WARNING | Warns when the agent switches between gcloud projects or AWS profiles mid-session |
| `operation-journal` | INFO | Records every Bash and file-write operation to an in-session audit log; emits a summary at Stop |
| `cloud-resource-deletion` | ERROR | Blocks AWS/GCP/Azure resource deletion without session confirmation |
| `cloud-infra-mutation` | ERROR | Blocks NAT, firewall, VPC, IAM, and load balancer mutations across AWS/GCP/Azure |
| `cloud-paid-resource-creation` | WARNING | Warns when creating paid cloud resources (VMs, DBs, static IPs) |
| `system-scheduler-guard` | WARNING | Warns on crontab, systemctl enable, launchctl, scheduler file writes |
| `network-firewall-guard` | ERROR | Blocks iptables flush, ufw disable, firewalld permanent rules, and default route changes |
| `docker-volume-guard` | WARNING/ERROR | Blocks privileged containers (ERROR); warns on volume deletion and force-remove (WARNING) |
| `ssh-destructive-command-guard` | WARNING/ERROR | Detects destructive commands via SSH (`rm -rf`, `mkfs`, `dd`, `reboot`, `iptables flush`, `terraform destroy`) |
| `remote-boot-partition-guard` | ERROR | Blocks `rm` or `dd` targeting `/boot` kernel and bootloader files via SSH |
| `remote-chroot-guard` | WARNING/ERROR | Detects bootloader package removal and risky repair commands inside chroot |
| `package-manager-in-chroot` | WARNING | Warns on `apt`/`dpkg`/`yum`/`dnf`/`pacman` usage inside chroot environments |
| `subagent-safety-briefing` | INFO | Injects safety notice into subagent context on spawn (SubagentStart) |
| `subagent-transcript-audit` | WARNING | Audits subagent transcripts for dangerous commands post-execution (SubagentStop) |

**Subagent safety:** Parent session hooks don't fire for subagent tool calls — this is a Claude Code architectural property. The autopilot pack addresses this with safety briefing injection (SubagentStart) and post-hoc transcript auditing (SubagentStop). AgentLint's own plugin agents also have frontmatter PreToolUse hooks for real-time blocking. See [docs/subagent-safety.md](docs/subagent-safety.md) for details.

Enable by adding `autopilot` to your packs list:

```yaml
packs:
  - universal
  - autopilot
```

Feedback welcome — open an issue if a rule blocks something legitimate or misses something it should catch.

</details>

### Stack auto-detection

When `stack: auto` (the default), AgentLint detects your project and activates matching packs:

| Detected file | Pack activated |
|--------------|----------------|
| `pyproject.toml` or `setup.py` | `python` |
| `package.json` | `frontend` |
| `react` in package.json dependencies | `react` |
| SSR/SSG framework in dependencies (Next.js, Nuxt, Gatsby, Astro, SvelteKit, Remix) | `seo` |
| `AGENTS.md` with relevant keywords | Additional packs based on content |

The `universal` and `quality` packs are always active. To override auto-detection, list packs explicitly in `agentlint.yml`.

## Quick start

```bash
pip install agentlint
cd your-project
agentlint setup
```

That's it! AgentLint hooks are now active in Claude Code. `agentlint setup` resolves the absolute path to the binary, so hooks work regardless of your shell's PATH — whether you installed via pip, pipx, uv, poetry, or a virtual environment.

When AgentLint blocks a dangerous action, the agent sees:

```
⛔ [no-secrets] Possible secret token detected (prefix 'sk_live_')
💡 Use environment variables instead of hard-coded secrets.
```

The agent's action is blocked before it can write the secret into your codebase.

The `setup` command:
- Installs hooks into `.claude/settings.json`
- Creates `agentlint.yml` with auto-detected settings (if it doesn't exist)

To remove AgentLint hooks:

```bash
agentlint uninstall
```

### Installation options

```bash
# Install to project (default)
agentlint setup

# Install to user-level settings (~/.claude/settings.json)
agentlint setup --global
```

### Claude Code marketplace

Add the AgentLint marketplace and install the plugin:

```
/plugin marketplace add mauhpr/agentlint-plugin
/plugin install agentlint@agentlint
```

### Local plugin (development)

```bash
claude --plugin-dir /path/to/agentlint/plugin
```

### Plugin agents

The AgentLint plugin includes specialized agents for multi-step operations:

- **`/agentlint:security-audit`** — Scan your codebase for security vulnerabilities, hardcoded secrets, and unsafe patterns
- **`/agentlint:doctor`** — Diagnose configuration issues, verify hook installation, suggest optimal pack settings
- **`/agentlint:fix`** — Auto-fix common violations (debug artifacts, accessibility, dead imports) with confirmation

### Manual hook configuration

> **Note:** The manual configuration below uses the bare `agentlint` command and requires it to be on your shell's PATH. For reliable resolution across all installation methods, use `agentlint setup` instead — it embeds the absolute path automatically.

`agentlint setup` registers 7 hook events. Add to your project's `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [{ "type": "command", "command": "agentlint check --event PreToolUse", "timeout": 5 }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "agentlint check --event PostToolUse", "timeout": 10 }]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [{ "type": "command", "command": "agentlint check --event UserPromptSubmit", "timeout": 5 }]
      }
    ],
    "SubagentStart": [
      {
        "hooks": [{ "type": "command", "command": "agentlint check --event SubagentStart", "timeout": 5 }]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [{ "type": "command", "command": "agentlint check --event SubagentStop", "timeout": 10 }]
      }
    ],
    "Notification": [
      {
        "hooks": [{ "type": "command", "command": "agentlint check --event Notification", "timeout": 5 }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "command", "command": "agentlint report", "timeout": 30 }]
      }
    ]
  }
}
```

## Configuration

Create `agentlint.yml` in your project root (or run `agentlint init`):

```yaml
# Auto-detect tech stack or list packs explicitly
stack: auto

# strict: warnings become errors
# standard: default behavior
# relaxed: warnings become info
severity: standard

packs:
  - universal
  # - security        # Opt-in: blocks Bash file writes, network exfiltration
  # - python          # Auto-detected from pyproject.toml / setup.py
  # - frontend        # Auto-detected from package.json
  # - react           # Auto-detected from react in dependencies
  # - seo             # Auto-detected from SSR/SSG framework in dependencies

rules:
  max-file-size:
    limit: 300          # Override default 500-line limit
  drift-detector:
    threshold: 5        # Warn after 5 edits without tests (default: 10)
  no-secrets:
    enabled: false      # Disable a rule entirely
  # Python pack examples:
  # no-bare-except:
  #   allow_reraise: true
  # Frontend pack examples:
  # a11y-heading-hierarchy:
  #   max_h1: 1

# Load custom rules from a directory
# custom_rules_dir: .agentlint/rules/
```

### AGENTS.md integration

AgentLint supports the [AGENTS.md](https://agents.md/) industry standard. Import conventions from your project's AGENTS.md into AgentLint config:

```bash
# Preview what would be generated
agentlint import-agents-md --dry-run

# Generate agentlint.yml from AGENTS.md
agentlint import-agents-md

# Merge with existing config
agentlint import-agents-md --merge
```

When `AGENTS.md` exists and `stack: auto` is set, AgentLint also uses it for pack auto-detection.

## Discovering rules

```bash
# List all rules (built-in + custom)
agentlint list-rules

# List rules in a specific pack (built-in or custom)
agentlint list-rules --pack security
agentlint list-rules --pack fintech

# List rules for a different project
agentlint list-rules --project-dir /path/to/project

# Show current status (version, packs, rule count, session activity)
agentlint status

# Diagnose common misconfigurations (including custom rules validation)
agentlint doctor

# Scan changed files for CI pipelines
agentlint ci --diff origin/main...HEAD
```

## Custom rules

Create a Python file in your custom rules directory:

```python
# .agentlint/rules/no_direct_db.py
from agentlint.models import Rule, RuleContext, Violation, Severity, HookEvent

class NoDirectDB(Rule):
    id = "no-direct-db"
    description = "API routes must not import database layer directly"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE]
    pack = "myproject"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if not context.file_path or "/routes/" not in context.file_path:
            return []
        if context.file_content and "from database" in context.file_content:
            return [Violation(
                rule_id=self.id,
                message="Route imports database directly. Use repository pattern.",
                severity=self.severity,
                file_path=context.file_path,
            )]
        return []
```

Then activate the pack in your config:

```yaml
packs:
  - universal
  - myproject      # activates all rules with pack = "myproject"

custom_rules_dir: .agentlint/rules/
```

Rules whose `pack` is not in `packs:` are loaded but silently skipped. Use `agentlint doctor` to detect orphaned packs.

## Monorepo Support

Different subdirectories can use different rule packs:

```yaml
packs:
  - universal          # fallback for files outside any project

projects:
  frontend/:
    packs: [universal, frontend, react]
  backend/:
    packs: [universal, python]
  infra/:
    packs: [universal, security, autopilot]
```

Files outside any project prefix use the global `packs:` list. Longest prefix wins for nested paths.

## MCP Server

Expose agentlint to Claude and other MCP clients. Agents can pre-validate code before writing:

```bash
pip install agentlint[mcp]
agentlint-mcp  # run via stdio
```

**Tools:**
- `check_content(content, file_path)` — pre-validate code against rules
- `list_rules(pack?)` — discover available rules
- `get_config()` — read current configuration

**Resources:** `agentlint://rules`, `agentlint://config`

## CI Mode

Run agentlint in CI pipelines — same rules, same config, different trigger:

```yaml
# .github/workflows/agentlint.yml
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

Only ERROR violations fail the build. Warnings are reported but don't block. Use `--format json` for machine-readable output.

## File-Scope Governance

Restrict which files the agent can access. Deny patterns take precedence over allow:

```yaml
rules:
  file-scope:
    allow: ["src/**", "tests/**", "docs/**"]
    deny: ["*.env", "credentials/**", ".github/workflows/**"]
```

Blocks Write, Edit, Read, and Bash file operations. Path traversal (`../`) is blocked. If no `file-scope` config is present, the rule is inactive.

## CLI Integration

Run any command-line tool as a PostToolUse check. AgentLint executes the command after Write/Edit and reports non-zero exit codes as violations:

```yaml
rules:
  cli-integration:
    commands:
      - name: ruff
        on: ["Write", "Edit"]
        glob: "**/*.py"
        command: "ruff check {file.path} --output-format=concise"
        timeout: 10
        severity: warning

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

### Available placeholders

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

Commands with unresolvable placeholders are silently skipped. All placeholder values are shell-escaped (`shlex.quote`) to prevent injection. File paths outside the project directory are rejected.

## How it works

AgentLint supports all 17 Claude Code hook events. `agentlint setup` registers 7 events out of the box:

| Event | When | Behavior |
|-------|------|----------|
| **PreToolUse** | Before Write/Edit/Bash | Can **block** the action |
| **PostToolUse** | After Write/Edit | Injects warnings into agent context |
| **UserPromptSubmit** | When user sends a prompt | Evaluates prompt-level rules |
| **SubagentStart** | When a subagent spawns | Injects safety briefing via `additionalContext` |
| **SubagentStop** | When a subagent completes | Audits subagent transcript for dangerous commands |
| **Notification** | On system notifications | Evaluates notification-triggered rules |
| **Stop** | End of session | Generates a quality report |

Custom rules can target any of the 17 events (SessionStart, PreCompact, WorktreeCreate, TaskCompleted, etc.).

Each invocation loads your config, evaluates matching rules, and returns JSON that Claude Code understands. Session state persists across invocations so rules like `drift-detector` can track cumulative behavior.

### Circuit breaker (Progressive Trust)

When a blocking rule fires repeatedly, it automatically degrades to avoid locking the agent in a loop:

| Fire count | Severity | Effect |
|-----------|----------|--------|
| 1-2 | ERROR | Blocks the action (normal) |
| 3-5 | WARNING | Advises instead of blocking |
| 6-9 | INFO | Appears in session report only |
| 10+ | Suppressed | Silent until reset |

The breaker resets after 5 consecutive clean evaluations or 30 minutes without firing.

Security-critical rules (`no-secrets`, `no-env-commit`) are exempt — they always block, regardless of fire count. Per-rule overrides are configurable:

```yaml
circuit_breaker:
  enabled: true          # ON by default
  degraded_after: 3      # ERROR -> WARNING
  passive_after: 6       # -> INFO
  open_after: 10         # -> suppressed

rules:
  max-file-size:
    circuit_breaker:
      degraded_after: 5  # Override per-rule
```

## Comparison with alternatives

| Project | How AgentLint differs |
|---------|----------------------|
| guardrails-ai | Validates LLM I/O. AgentLint validates agent *tool calls* in real-time. |
| claude-code-guardrails | Uses external API. AgentLint is local-first, no network dependency. |
| Custom hooks | Copy-paste scripts. AgentLint is a composable engine with config + plugins. |
| Codacy Guardrails | Commercial, proprietary. AgentLint is fully open source. |

## FAQ

**Does AgentLint slow down Claude Code?**
No. Rules evaluate in <10ms. AgentLint runs locally as a subprocess — no network calls, no API dependencies.

**What if a rule is too strict for my project?**
Disable it in `agentlint.yml`: `rules: { no-secrets: { enabled: false } }`. Or switch to `severity: relaxed` to downgrade warnings to informational. The circuit breaker also helps — if a rule fires 3+ times in a session, it automatically degrades from blocking to advisory.

**Is my code sent anywhere?**
No. AgentLint is fully offline. It reads stdin from Claude Code's hook system and evaluates rules locally. No telemetry, no network requests.

**Can I use AgentLint outside Claude Code?**
The CLI works standalone — you can pipe JSON to `agentlint check` in any CI pipeline. However, the hook integration (blocking actions in real-time) is specific to Claude Code.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

MIT
