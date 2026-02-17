# agentlint

Real-time quality guardrails for AI coding agents.

AI coding agents drift during long sessions — they introduce API keys into source, skip tests, force-push to main, and leave debug statements behind. AgentLint catches these problems *as they happen*, not at review time.

## What it catches

AgentLint ships with 10 universal rules that work with any tech stack:

| Rule | Severity | What it does |
|------|----------|-------------|
| `no-secrets` | ERROR | Blocks writes containing API keys, tokens, passwords |
| `no-env-commit` | ERROR | Blocks writing `.env` and credential files |
| `no-force-push` | ERROR | Blocks `git push --force` to main/master |
| `no-destructive-commands` | WARNING | Warns on `rm -rf`, `DROP TABLE`, `git reset --hard` |
| `dependency-hygiene` | WARNING | Warns on ad-hoc `pip install` / `npm install` |
| `max-file-size` | WARNING | Warns when a file exceeds 500 lines |
| `drift-detector` | WARNING | Warns after many edits without running tests |
| `no-debug-artifacts` | WARNING | Detects `console.log`, `print()`, `debugger` left in code |
| `test-with-changes` | WARNING | Warns if source changed but no tests were updated |
| `no-todo-left` | INFO | Reports TODO/FIXME comments in changed files |

**ERROR** rules block the agent's action. **WARNING** rules inject advice into the agent's context. **INFO** rules appear in the session report.

## Quick start

```bash
pip install agentlint
cd your-project
agentlint setup
```

That's it! AgentLint hooks are now active in Claude Code. The `setup` command:
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
/plugin marketplace add mauhpr/agentlint
/plugin install agentlint@agentlint
```

### Local plugin (development)

```bash
claude --plugin-dir /path/to/agentlint/plugin
```

### Manual hook configuration

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

rules:
  max-file-size:
    limit: 300          # Override default 500-line limit
  drift-detector:
    threshold: 5        # Warn after 5 edits without tests (default: 10)
  no-secrets:
    enabled: false      # Disable a rule entirely

# Load custom rules from a directory
# custom_rules_dir: .agentlint/rules/
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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

MIT
