# agentlint

[![CI](https://github.com/mauhpr/agentlint/actions/workflows/ci.yml/badge.svg)](https://github.com/mauhpr/agentlint/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/mauhpr/agentlint/branch/main/graph/badge.svg)](https://codecov.io/gh/mauhpr/agentlint)
[![PyPI](https://img.shields.io/pypi/v/agentlint)](https://pypi.org/project/agentlint/)
[![Python](https://img.shields.io/pypi/pyversions/agentlint)](https://pypi.org/project/agentlint/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Real-time quality guardrails for AI coding agents.

AI coding agents drift during long sessions — they introduce API keys into source, skip tests, force-push to main, and leave debug statements behind. AgentLint catches these problems *as they happen*, not at review time.

## What it catches

AgentLint ships with 41 rules across 7 packs, covering all 17 Claude Code hook events. The 14 **universal** rules and 4 **quality** rules work with any tech stack; 4 additional packs auto-activate based on your project files, and the **security** pack is opt-in for maximum protection:

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
| `no-todo-left` | INFO | Reports TODO/FIXME comments in changed files |

**ERROR** rules block the agent's action. **WARNING** rules inject advice into the agent's context. **INFO** rules appear in the session report.

<details>
<summary><strong>Quality pack</strong> (4 rules) — always active alongside universal</summary>

| Rule | Severity | What it does |
|------|----------|-------------|
| `commit-message-format` | WARNING | Validates commit messages follow conventional format |
| `no-error-handling-removal` | WARNING | Warns when try/except or .catch() blocks are removed |
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
<summary><strong>Security pack</strong> (2 rules) — opt-in, add <code>security</code> to your packs list</summary>

| Rule | Severity | What it does |
|------|----------|-------------|
| `no-bash-file-write` | ERROR | Blocks file writes via Bash (`cat >`, `tee`, `sed -i`, `cp`, heredocs, etc.) |
| `no-network-exfil` | ERROR | Blocks data exfiltration via `curl POST`, `nc`, `scp`, `wget --post-file` |

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

### Stack auto-detection

When `stack: auto` (the default), AgentLint detects your project and activates matching packs:

| Detected file | Pack activated |
|--------------|----------------|
| `pyproject.toml` or `setup.py` | `python` |
| `package.json` | `frontend` |
| `react` in package.json dependencies | `react` |
| SSR/SSG framework in dependencies (Next.js, Nuxt, Gatsby, Astro, SvelteKit, Remix) | `seo` |

The `universal` pack is always active. To override auto-detection, list packs explicitly in `agentlint.yml`.

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

### Manual hook configuration

> **Note:** The manual configuration below uses the bare `agentlint` command and requires it to be on your shell's PATH. For reliable resolution across all installation methods, use `agentlint setup` instead — it embeds the absolute path automatically.

Add to your project's `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [{ "type": "command", "command": "agentlint check --event PreToolUse" }]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "agentlint check --event PostToolUse" }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "command", "command": "agentlint report" }]
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

## Discovering rules

```bash
# List all available rules
agentlint list-rules

# List rules in a specific pack
agentlint list-rules --pack security

# Show current status (version, packs, rule count, session activity)
agentlint status

# Diagnose common misconfigurations
agentlint doctor
```

## Custom rules

Create a Python file in your custom rules directory:

```python
# .agentlint/rules/no_direct_db.py
from agentlint.models import Rule, RuleContext, Violation, Severity, HookEvent

class NoDirectDB(Rule):
    id = "custom/no-direct-db"
    description = "API routes must not import database layer directly"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE]
    pack = "custom"

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

Then set `custom_rules_dir: .agentlint/rules/` in your config.

See [docs/custom-rules.md](docs/custom-rules.md) for the full guide.

## How it works

AgentLint hooks into Claude Code's lifecycle events:

1. **PreToolUse** — Before Write/Edit/Bash calls. Can **block** the action (exit code 2).
2. **PostToolUse** — After Write/Edit. Injects warnings into the agent's context.
3. **Stop** — End of session. Generates a quality report.

Each invocation loads your config, evaluates matching rules, and returns JSON that Claude Code understands. Session state persists across invocations so rules like `drift-detector` can track cumulative behavior.

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
Disable it in `agentlint.yml`: `rules: { no-secrets: { enabled: false } }`. Or switch to `severity: relaxed` to downgrade warnings to informational.

**Is my code sent anywhere?**
No. AgentLint is fully offline. It reads stdin from Claude Code's hook system and evaluates rules locally. No telemetry, no network requests.

**Can I use AgentLint outside Claude Code?**
The CLI works standalone — you can pipe JSON to `agentlint check` in any CI pipeline. However, the hook integration (blocking actions in real-time) is specific to Claude Code.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

MIT
