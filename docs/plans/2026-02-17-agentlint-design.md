# AgentLint — Design Document

**Date:** 2026-02-17
**Author:** maupr92
**Status:** Approved

## Problem

AI coding agents (Claude Code, Cursor, Codex) drift during long sessions. They introduce security vulnerabilities, skip tests, violate architectural conventions, and accumulate quality debt — all without the developer noticing until review time. Current solutions are fragmented: standalone hooks with no shared state, security-only guardrails, or commercial products.

## Solution

AgentLint is an open-source, real-time quality guardrail framework for AI coding agents. It works like ESLint but for agent behavior — evaluating every tool call against configurable rule packs and blocking or warning before damage is done.

## Architecture

Three concentric layers:

```
┌──────────────────────────────────────────────────┐
│             Claude Code Plugin (UX layer)         │
│  hooks/     → thin wrappers calling engine CLI    │
│  commands/  → /lint-status, /lint-config          │
│  agents/    → lint-reviewer subagent              │
│  mcp/       → query rules, state, overrides       │
├──────────────────────────────────────────────────┤
│             Core Engine (pip install agentlint)   │
│  engine.py  → orchestrator: config → detect → run │
│  rule.py    → Rule base class, Violation, Context │
│  config.py  → parse agentlint.yml + auto-detect   │
│  detector.py→ stack detection from project files  │
│  reporter.py→ format output for Claude Code       │
│  session.py → shared state across rule evals      │
│  cli.py     → agentlint check, init, report       │
├──────────────────────────────────────────────────┤
│             Rule Packs                            │
│  universal │ python │ react │ rails │ custom      │
└──────────────────────────────────────────────────┘
```

## Core Rule Interface

```python
class Severity(Enum):
    ERROR = "error"      # Blocks the tool call (exit code 2)
    WARNING = "warning"  # Shows warning, allows tool call
    INFO = "info"        # Advisory, shown in report only

class HookEvent(Enum):
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    STOP = "Stop"
    SESSION_START = "SessionStart"

@dataclass
class Violation:
    rule_id: str
    message: str
    severity: Severity
    file_path: str | None
    line: int | None
    suggestion: str | None

@dataclass
class RuleContext:
    event: HookEvent
    tool_name: str
    tool_input: dict
    file_path: str | None
    file_content: str | None
    project_dir: str
    config: dict
    session_state: dict      # Shared mutable state across rules

class Rule:
    id: str
    description: str
    severity: Severity
    events: list[HookEvent]
    pack: str

    def evaluate(self, context: RuleContext) -> list[Violation]:
        raise NotImplementedError
```

## Rule Packs

### Universal (always active)

| Rule ID | Event | Default Severity | Description |
|---------|-------|------------------|-------------|
| `no-secrets` | PreToolUse | ERROR | Blocks writing API keys, tokens, passwords |
| `no-env-commit` | PreToolUse | ERROR | Blocks writing .env, credentials files |
| `test-with-changes` | Stop | WARNING | Warns if source changed but no tests touched |
| `no-todo-left` | Stop | INFO | Reports TODO/FIXME/HACK in changed files |
| `max-file-size` | PostToolUse | WARNING | Warns if file exceeds 500 lines (configurable) |
| `no-force-push` | PreToolUse | ERROR | Blocks git push --force to main/master |
| `no-destructive-commands` | PreToolUse | WARNING | Warns on rm -rf, DROP TABLE, git reset --hard |
| `dependency-hygiene` | PreToolUse | WARNING | Warns on pip install (use poetry/uv), npm install (use npm ci) |
| `no-debug-artifacts` | Stop | WARNING | Detects console.log, print(), debugger in non-test files |
| `drift-detector` | PostToolUse | WARNING | After N file edits without test run, warns to run tests |

### Python (auto-detected via pyproject.toml)

| Rule ID | Event | Default Severity | Description |
|---------|-------|------------------|-------------|
| `python-type-hints` | PostToolUse | WARNING | Functions must have return type annotations |
| `python-no-print` | PostToolUse | WARNING | print() in non-test code, use logging |
| `python-import-order` | PostToolUse | INFO | stdlib, third-party, local import grouping |
| `python-poetry-only` | PreToolUse | ERROR | Blocks pip install, requirements.txt creation |
| `python-no-bare-except` | PostToolUse | WARNING | Catches bare except: without specific exception |

### React/TypeScript (auto-detected via package.json with react)

| Rule ID | Event | Default Severity | Description |
|---------|-------|------------------|-------------|
| `react-accessibility` | PostToolUse | WARNING | img alt, button names, form labels, ARIA |
| `react-mobile-first` | PostToolUse | WARNING | Touch targets >= 44px, no hover-only, responsive |
| `react-no-inline-styles` | PostToolUse | INFO | Prefer Tailwind/CSS modules over inline styles |
| `react-hooks-rules` | PostToolUse | WARNING | Hooks called conditionally or in loops |
| `react-i18n-hardcoded` | PostToolUse | WARNING | Hardcoded user-facing strings, should use i18n |

### Custom Rules

Users create rules in `.agentlint/rules/` using the same Rule interface:

```python
# .agentlint/rules/no_direct_db.py
from agentlint import Rule, RuleContext, Violation, Severity, HookEvent

class NoDirectDB(Rule):
    id = "custom/no-direct-db"
    description = "API routes must not import from database layer directly"
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
                line=None,
                suggestion="Import from services/ or repositories/ instead"
            )]
        return []
```

## Configuration

### agentlint.yml

```yaml
stack: auto          # auto-detect from project files
severity: standard   # strict | standard | relaxed

packs:
  - universal
  - python           # auto-detected
  - react            # auto-detected

rules:
  no-secrets:
    severity: error
  max-file-size:
    limit: 500
  drift-detector:
    threshold: 10

# custom_rules_dir: .agentlint/rules/
```

### Severity Modes

- **strict**: All warnings become errors (blocks agent). For production/financial code.
- **standard**: Errors block, warnings shown. Default.
- **relaxed**: Only critical errors block. For prototyping.

### Auto-Detection

The detector scans project root for:

| Signal | Pack Activated |
|--------|---------------|
| `pyproject.toml` or `setup.py` | python |
| `package.json` with `react` | react |
| `Gemfile` with `rails` | rails (future) |
| `go.mod` | go (future) |
| Always | universal |

## Execution Flow

```
Claude Code hook fires (PreToolUse/PostToolUse/Stop)
        │
        ▼
Thin shell wrapper pipes stdin to: agentlint check --event <event>
        │
        ▼
Engine loads agentlint.yml (or auto-detected defaults)
        │
        ▼
Build RuleContext from stdin JSON + file content + git state
        │
        ▼
Filter rules: matching event + active packs + enabled
        │
        ▼
Evaluate rules (parallel where no state dependency)
        │
        ▼
Collect Violations, determine exit code
        │
        ▼
Report: JSON to stdout (Claude Code protocol)
  - exit 0: all passed
  - exit 2: blocking error (PreToolUse only)
  - systemMessage: warnings/info injected into agent context
```

## Claude Code Plugin Structure

```
agentlint-plugin/
├── plugin.json
├── hooks/
│   ├── pre-tool-use.sh        # cat | agentlint check --event PreToolUse
│   ├── post-tool-use.sh       # cat | agentlint check --event PostToolUse
│   └── stop.sh                # agentlint report
├── commands/
│   ├── lint-status.md         # /lint-status
│   └── lint-config.md         # /lint-config
├── agents/
│   └── lint-reviewer.md       # Deep review subagent
└── mcp/
    └── server.py              # Optional MCP server
```

## MCP Server (Optional)

Exposes tools for agent self-correction:

| Tool | Description |
|------|-------------|
| `get_active_rules()` | List rules currently active |
| `get_session_violations()` | All violations this session |
| `check_file(path)` | Pre-check a file before writing |
| `suppress_rule(rule_id, reason)` | Temporarily suppress with logged reason |

## Developer Experience

### Installation

```bash
# As Claude Code plugin (recommended)
claude plugin add agentlint

# Standalone
pip install agentlint
agentlint init
```

### Slash Commands

| Command | Description |
|---------|-------------|
| `/lint-status` | Active rules, violations this session, severity counts |
| `/lint-config` | Current config, active packs, overridden rules |
| `/lint-suppress <rule> "<reason>"` | Temporarily suppress a rule |

### Session Report (Stop event)

```
AgentLint Session Report
Files changed: 12  |  Rules evaluated: 847
Passed: 834  |  Warnings: 11  |  Blocked: 2

Blocked actions:
  no-secrets: Attempted to write API key in config.py (line 23)
  no-force-push: Blocked git push --force to main

Warnings:
  test-with-changes: 8 source files changed, 0 test files changed
  drift-detector: 12 files modified since last test run
  react-accessibility: 3 components missing alt attributes
```

## Project Structure (Full)

```
agentlint/
├── pyproject.toml
├── README.md
├── LICENSE                    # MIT
├── agentlint.yml.example
├── src/
│   └── agentlint/
│       ├── __init__.py
│       ├── engine.py          # Orchestrator
│       ├── rule.py            # Rule, Violation, RuleContext
│       ├── config.py          # Config parser
│       ├── detector.py        # Stack auto-detection
│       ├── reporter.py        # Claude Code output formatter
│       ├── session.py         # Session state manager
│       ├── cli.py             # CLI (click-based)
│       ├── packs/
│       │   ├── __init__.py    # Pack registry
│       │   ├── universal/
│       │   │   ├── __init__.py
│       │   │   ├── no_secrets.py
│       │   │   ├── no_env_commit.py
│       │   │   ├── test_with_changes.py
│       │   │   ├── no_todo_left.py
│       │   │   ├── max_file_size.py
│       │   │   ├── no_force_push.py
│       │   │   ├── no_destructive_commands.py
│       │   │   ├── dependency_hygiene.py
│       │   │   ├── no_debug_artifacts.py
│       │   │   └── drift_detector.py
│       │   ├── python/
│       │   │   ├── __init__.py
│       │   │   ├── type_hints.py
│       │   │   ├── no_print.py
│       │   │   ├── import_order.py
│       │   │   ├── poetry_only.py
│       │   │   └── no_bare_except.py
│       │   └── react/
│       │       ├── __init__.py
│       │       ├── accessibility.py
│       │       ├── mobile_first.py
│       │       ├── no_inline_styles.py
│       │       ├── hooks_rules.py
│       │       └── i18n_hardcoded.py
│       └── utils/
│           ├── __init__.py
│           ├── patterns.py    # Shared regex (secrets, etc.)
│           └── git.py         # Git helpers
├── plugin/                    # Claude Code plugin
│   ├── plugin.json
│   ├── hooks/
│   ├── commands/
│   ├── agents/
│   └── mcp/
└── tests/
    ├── test_engine.py
    ├── test_config.py
    ├── test_detector.py
    ├── packs/
    │   ├── test_universal.py
    │   ├── test_python.py
    │   └── test_react.py
    └── fixtures/
        ├── sample_projects/
        └── tool_inputs/
```

## Implementation Phases

### Phase 1: Core + Universal Pack (MVP)
- Rule interface, engine, config parser, CLI
- Universal rule pack (10 rules)
- Claude Code plugin with hooks
- `agentlint init` with auto-detection
- Tests for all rules

### Phase 2: Framework Packs
- Python pack (5 rules)
- React/TypeScript pack (5 rules)
- Custom rules support (.agentlint/rules/)

### Phase 3: Intelligence Layer
- Session state + drift detector
- MCP server for agent self-correction
- /lint-status, /lint-config commands
- Session report on Stop

### Phase 4: Community & Ecosystem
- Rule contribution guide
- Rule testing framework
- Published to PyPI + Claude Code plugin marketplace
- GitHub Actions integration
- Additional packs (Rails, Go, Next.js)

## Competitive Landscape

| Project | How AgentLint Differs |
|---------|----------------------|
| guardrails-ai | They validate LLM I/O. We validate agent tool calls in real-time. |
| rulebricks/claude-code-guardrails | They use external API. We're local-first, no network dependency. |
| disler/claude-code-hooks-mastery | Demo/learning focused. We're a production framework. |
| M87-Spine-lite | Security/governance focused. We cover quality + architecture + security. |
| Codacy Guardrails | Commercial, proprietary CLI. We're fully open source. |
| karanb192/claude-code-hooks | Copy-paste hooks. We're composable engine with config. |

## Key Design Decisions

1. **Python-first engine**: Most Claude Code hooks are Python. Rules are Python classes. The ecosystem is familiar.
2. **Thin shell wrappers**: Plugin hooks are 1-line shell scripts calling the engine. All logic is in the pip package — testable, versionable, portable.
3. **Auto-detect + override**: Zero-config to start, full customization via agentlint.yml. Reduces friction.
4. **Session state**: Rules share state within a session, enabling cross-rule intelligence (drift detection, cumulative warnings).
5. **MCP as optional upgrade**: The MCP server enables agent self-correction but isn't required for basic guardrails.
6. **Blocking only on PreToolUse**: PostToolUse and Stop rules advise but never block (the action already happened). Only PreToolUse rules can return exit code 2 to prevent an action.
