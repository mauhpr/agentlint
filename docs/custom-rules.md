# Custom Rules Guide

AgentLint lets you create project-specific rules using the same interface as built-in rules. Custom rules are Python files placed in a directory of your choice.

## Setup

1. Create a rules directory in your project:

```bash
mkdir -p .agentlint/rules
```

2. Enable it in `agentlint.yml`:

```yaml
custom_rules_dir: .agentlint/rules/
```

## Creating a rule

Create a `.py` file in your custom rules directory. Each file can contain one or more `Rule` subclasses.

```python
# .agentlint/rules/no_raw_sql.py
from agentlint.models import Rule, RuleContext, Violation, Severity, HookEvent


class NoRawSQL(Rule):
    id = "custom/no-raw-sql"
    description = "Blocks raw SQL queries — use the ORM instead"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "custom"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        content = context.file_content or ""
        if not content:
            return []

        # Check for raw SQL patterns
        sql_keywords = ["execute(", "raw_sql(", "cursor.execute("]
        for keyword in sql_keywords:
            if keyword in content:
                return [Violation(
                    rule_id=self.id,
                    message=f"Raw SQL detected ({keyword}). Use the ORM.",
                    severity=self.severity,
                    file_path=context.file_path,
                    suggestion="Use Model.objects or the query builder instead.",
                )]
        return []
```

## Rule anatomy

Every rule needs these class attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `str` | Unique identifier. Prefix with `custom/` for clarity. |
| `description` | `str` | One-line description. |
| `severity` | `Severity` | `ERROR` (blocks), `WARNING` (advises), or `INFO` (reports). |
| `events` | `list[HookEvent]` | When this rule runs. |
| `pack` | `str` | Set to `"custom"` for custom rules. |

And one method:

```python
def evaluate(self, context: RuleContext) -> list[Violation]:
    """Return a list of violations (empty list = pass)."""
```

## RuleContext fields

Your `evaluate` method receives a `RuleContext` with:

| Field | Type | Description |
|-------|------|-------------|
| `event` | `HookEvent` | Current lifecycle event |
| `tool_name` | `str` | Tool being used (Write, Edit, Bash, etc.) |
| `tool_input` | `dict` | Raw tool input from Claude Code |
| `project_dir` | `str` | Absolute path to project root |
| `file_content` | `str \| None` | File content (for Write/Edit operations) |
| `file_path` | `str \| None` | Target file path (from `tool_input`) |
| `command` | `str \| None` | Bash command (from `tool_input`) |
| `config` | `dict` | Per-rule config from `agentlint.yml` |
| `session_state` | `dict` | Mutable shared state across the session |

## Hook events

Choose which events your rule responds to:

| Event | When | Can block? |
|-------|------|-----------|
| `HookEvent.PRE_TOOL_USE` | Before a tool call | Yes (ERROR = exit code 2) |
| `HookEvent.POST_TOOL_USE` | After a tool call | No (advise only) |
| `HookEvent.STOP` | End of session | No (report only) |

## Using session state

Rules can share state across invocations using `context.session_state`. This is a mutable dict persisted between hook calls:

```python
def evaluate(self, context: RuleContext) -> list[Violation]:
    state = context.session_state
    state["my_counter"] = state.get("my_counter", 0) + 1
    # State persists to the next invocation
    ...
```

## Testing your rule

```python
# tests/test_my_rule.py
from agentlint.models import HookEvent, RuleContext
from your_rules.no_raw_sql import NoRawSQL


def test_detects_raw_sql():
    rule = NoRawSQL()
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": "app/views.py"},
        project_dir="/tmp",
        file_content="cursor.execute('SELECT * FROM users')",
    )
    violations = rule.evaluate(context)
    assert len(violations) == 1
    assert "Raw SQL" in violations[0].message


def test_passes_orm_code():
    rule = NoRawSQL()
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": "app/views.py"},
        project_dir="/tmp",
        file_content="users = User.objects.filter(active=True)",
    )
    assert rule.evaluate(context) == []
```

## File naming

- Files starting with `_` are skipped (e.g., `_helpers.py`)
- Each `.py` file is scanned for `Rule` subclasses
- Multiple rule classes per file are supported
