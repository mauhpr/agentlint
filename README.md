# agentlint

[![CI](https://github.com/mauhpr/agentlint/actions/workflows/ci.yml/badge.svg)](https://github.com/mauhpr/agentlint/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/mauhpr/agentlint/branch/main/graph/badge.svg)](https://codecov.io/gh/mauhpr/agentlint)
[![PyPI](https://img.shields.io/pypi/v/agentlint)](https://pypi.org/project/agentlint/)
[![Python](https://img.shields.io/pypi/pyversions/agentlint)](https://pypi.org/project/agentlint/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Real-time guardrails for AI coding agents — code quality, security, and infrastructure safety.

Works with **Claude Code**, **Cursor**, **Kimi**, **Grok**, **Gemini**, **Codex**, **Continue.dev**, **OpenAI Agents SDK**, **MCP hosts**, and custom frameworks.

AI coding agents drift during long sessions — they introduce API keys into source, skip tests, force-push to main, and leave debug statements behind. AgentLint catches these problems *as they happen*, not at review time.

Architecture overview: [docs/architecture.md](docs/architecture.md)

## Vision

The short-term problem is code quality: secrets, broken tests, force-pushes, debug artifacts. AgentLint solves that today with 76 rules that run locally in milliseconds.

The longer-term question is harder: **what does it mean for an agent to operate safely on real infrastructure?** When an agent can run `gcloud`, `kubectl`, `terraform`, or `iptables`, the blast radius is no longer a bad commit — it's a production outage or a deleted database.

We don't have a mature answer to that yet. Nobody does. The **autopilot pack** is our first experiment in that direction — explicit, opt-in, and clearly labeled as such. The goal is to start building the intuition and tooling for autonomous agent safety at the infrastructure level, and to do it in the open.

## What it catches

AgentLint ships with 76 rules across 8 packs and normalizes tool events across supported AI coding agents. The 23 **universal** rules and 7 **quality** rules work with any tech stack; 4 additional packs auto-activate based on your project files; the **security** pack is opt-in; and the **autopilot** pack is opt-in and experimental.

**v2.3.1 highlights:** AgentChute onboarding polish with clearer local setup output, Codex hook enablement guidance, safer sync dry-run diagnostics, FastAPI-aware `no-unnecessary-async`, grouped text CI findings, and repo-local accepted patterns through per-rule `ignore_paths`. Previous: Install experience polish, `agentlint --version`, AgentChute sync support from the default `pip install agentlint` package, public documentation cleanup, AgentChute-ready team sync, hybrid cloud feeds, privacy-safe event queueing, multi-platform adapter architecture, unified `AgentEvent` taxonomy, `NormalizedTool` cross-platform mappings, session summary dashboard, MCP server, global config defaults, warning suppression, auto-suppress, `diff_only` mode, and `auto-fix` mode.

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
| `cicd-pipeline-guard` | ERROR | Blocks CI/CD pipeline changes without approval |
| `package-publish-guard` | ERROR | Blocks `npm publish`, `twine upload`, `gem push` |
| `file-scope` | ERROR | Restricts file access via allow/deny globs |
| `cli-integration` | configurable | Runs external CLI tools (ruff, eslint, etc.) on file changes |
| `git-checkpoint` | INFO | Creates git stash before destructive ops (opt-in, disabled by default) |
| `no-todo-left` | INFO | Reports TODO/FIXME comments in changed files |
| `no-compromised-dependency` | ERROR | Blocks installs of packages on AgentChute's compromised-package feed |
| `no-vulnerable-version-install` | ERROR | Blocks pinned installs of versions known vulnerable in GHSA data |
| `no-vulnerable-import` | WARNING | Warns when importing packages with active GHSA advisories |
| `token-burn-against-team-budget` | WARNING | Warns when AgentChute reports team-level budget pressure |

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
| `no-unnecessary-async` | INFO | Flags async functions that never use `await`; skips FastAPI route handlers by default |
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
<summary><strong>Security pack</strong> (7 rules) — opt-in, add <code>security</code> to your packs list</summary>

| Rule | Severity | What it does |
|------|----------|-------------|
| `no-bash-file-write` | ERROR | Blocks file writes via Bash (`cat >`, `tee`, `sed -i`, `cp`, heredocs, etc.) |
| `no-network-exfil` | ERROR | Blocks data exfiltration via `curl POST`, `nc`, `scp`, `wget --post-file` |
| `env-credential-reference` | WARNING | Warns when `*_FILE` env vars reference local paths (credential leakage risk) |
| `no-leaked-secret-pattern` | ERROR | Blocks patterns from AgentChute's cloud-curated secret ruleset |
| `no-malicious-url-fetch` | ERROR | Blocks fetches of known-malicious URLs from URLhaus-derived feeds |
| `no-blocked-domain-fetch` | ERROR | Blocks fetches from blocked malware/ad/tracker domains |
| `no-compromised-action` | ERROR | Blocks GitHub Actions pinned to compromised advisories |

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

Per-rule accepted patterns can be documented locally:

```yaml
rules:
  no-unnecessary-async:
    ignore_paths:
      - "app/api/*_routes.py"
    reason: "FastAPI route consistency"
```

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

Pick the AI coding agent you actually use:

```bash
pip install agentlint
cd your-project
agentlint setup claude    # Claude Code
agentlint setup cursor    # Cursor
agentlint setup codex     # Codex CLI
agentlint setup gemini    # Gemini CLI
```

Run `agentlint setup --help` for the full platform list. `agentlint setup` resolves the absolute path to the binary, so hooks work regardless of your shell's PATH — whether you installed via pip, pipx, uv, poetry, or a virtual environment.

When AgentLint blocks a dangerous action, the agent sees:

```
⛔ [no-secrets] Possible secret token detected (prefix 'sk_live_')
💡 Use environment variables instead of hard-coded secrets.
```

The agent's action is blocked before it can write the secret into your codebase.

The `setup` command:
- Installs hooks or guardrails for the selected agent platform
- Creates `agentlint.yml` with auto-detected settings (if it doesn't exist)

To remove AgentLint hooks:

```bash
agentlint uninstall
```

### Installation options

| Platform | Setup command | Integration style |
| --- | --- | --- |
| Claude Code | `agentlint setup claude` | Native hooks in `.claude/settings.json` or user settings |
| Cursor IDE | `agentlint setup cursor` | Native hooks in `.cursor/hooks.json` |
| Codex CLI | `agentlint setup codex` | Native hooks in `.codex/hooks.json`; Bash coverage is strongest |
| Gemini CLI | `agentlint setup gemini` | Native hooks in `.gemini/settings.json` |
| Continue.dev | `agentlint setup continue` | Native hooks in `.continue/settings.json` |
| Kimi Code CLI | `agentlint setup kimi` | Native TOML hooks |
| Grok CLI | `agentlint setup grok` | Native JSON hooks |
| OpenAI Agents SDK | `agentlint setup openai` | Guardrail integration code |
| MCP hosts | `agentlint setup mcp` | MCP server config |
| Custom tools | `agentlint setup generic` | Generic normalized HTTP/webhook adapter |

For platform-specific details, use the setup guides in `docs/`:

- [Claude Code](docs/setup-claude.md)
- [Cursor](docs/setup-cursor.md)
- [Codex](docs/setup-codex.md)
- [Gemini](docs/setup-gemini.md)
- [Kimi](docs/setup-kimi.md)
- [Grok](docs/setup-grok.md)
- [Continue.dev](docs/setup-continue.md)
- [OpenAI Agents SDK](docs/setup-openai.md)
- [MCP hosts](docs/setup-mcp.md)
- [Generic integrations](docs/setup-generic.md)

### Claude Code marketplace plugin

Claude Code users can also install the marketplace wrapper from
[`mauhpr/agentlint-plugin`](https://github.com/mauhpr/agentlint-plugin). The
plugin repo contains Claude-specific marketplace metadata, hook files, and
plugin commands; this repo contains the core engine and cross-platform setup.

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
    threshold: 5        # Warn after 5 edits without tests (default: 15)
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

### AgentChute opt-in

AgentLint runs locally by default. No event data leaves your machine unless you enable AgentChute with a license key and an explicit opt-in:

```bash
pip install agentlint
agentlint --version
agentlint init --team-key=ac_team_...
```

That enables AgentChute in `agentlint.yml` and prints the env vars to add to your shell, CI, or AI tool settings. The plaintext key is not written to repo config.

```yaml
agentchute:
  enabled: true
```

```bash
export AGENTCHUTE_LICENSE_KEY=ac_team_...
export AGENTCHUTE_ENABLED=true
# Optional for self-hosted/local API:
export AGENTCHUTE_API_URL=http://localhost:8000/v1
```

When enabled, AgentLint sends privacy-safe event summaries only: file paths and lengths for writes/edits, truncated Bash command previews, truncated prompt previews, violation metadata, and rule counts. It never sends raw file contents, full edit strings, or full prompts.

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

Expose agentlint to Claude and other MCP clients. Agents can **pre-validate code before writing**, eliminating the block-retry loop where hooks reject code and the agent rewrites multiple times.

```bash
pip install agentlint[mcp]
agentlint-mcp  # run via stdio
```

**Tools:**
- `check_content(content, file_path)` — pre-validate code against rules
- `list_rules(pack?)` — discover available rules
- `get_config()` — read current configuration
- `suppress_rule(rule_id)` — suppress a warning for the session (ERRORs always enforced)

**Resources:** `agentlint://rules`, `agentlint://config`

See [docs/mcp.md](docs/mcp.md) for the full MCP guide with workflow recipes and troubleshooting.

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

AgentLint normalizes each platform's hook or guardrail payload into a shared event model. Claude Code has the broadest native lifecycle coverage today: all 17 Claude Code hook events are understood, and `agentlint setup claude` registers 7 high-value runtime events out of the box:

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

Each invocation loads your config, evaluates matching rules, and returns the protocol response expected by the selected adapter. Session state persists across invocations so rules like `drift-detector` can track cumulative behavior.

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

**Does AgentLint slow down my AI coding agent?**
No. Rules evaluate in <10ms. AgentLint runs locally as a subprocess — no network calls, no API dependencies.

**What if a rule is too strict for my project?**
Disable it in `agentlint.yml`: `rules: { no-secrets: { enabled: false } }`. Or switch to `severity: relaxed` to downgrade warnings to informational. The circuit breaker also helps — if a rule fires 3+ times in a session, it automatically degrades from blocking to advisory.

**Is my code sent anywhere?**
No. AgentLint is fully offline by default. It reads the local hook, guardrail, MCP, or webhook payload and evaluates rules locally. No telemetry, no network requests. AgentChute sync is a separate opt-in path and sends only privacy-safe event summaries.

**Can I use AgentLint outside Claude Code?**
Yes. AgentLint supports real-time blocking hooks on Claude Code, Cursor, Kimi, Grok, Gemini, Codex, and Continue.dev. For OpenAI Agents SDK and MCP hosts, use guardrail-based integration. The CLI also works standalone in any CI pipeline.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

MIT
