# Custom rules

You can add project-specific rules written in Python. Custom rules use the same
`Rule` interface as the built-in rules and run in the same engine, for every
supported agent.

## Quick start

1. Create a rules directory in your project:

   ```bash
   mkdir -p .agentlint/rules
   ```

2. Add a rule file:

   ```python
   # .agentlint/rules/no_direct_db.py
   from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation


   class NoDirectDB(Rule):
       id = "no-direct-db"
       description = "API routes must not import the database layer directly"
       severity = Severity.WARNING
       events = [HookEvent.POST_TOOL_USE]
       pack = "myproject"

       def evaluate(self, context: RuleContext) -> list[Violation]:
           if not context.file_path or "/routes/" not in context.file_path:
               return []
           if context.file_content and "from database" in context.file_content:
               return [
                   Violation(
                       rule_id=self.id,
                       message="Route imports the database directly. Use the repository layer.",
                       severity=self.severity,
                       file_path=context.file_path,
                   )
               ]
           return []
   ```

3. Point `agentlint.yml` at the directory and activate the pack:

   ```yaml
   packs:
     - python
     - myproject          # activates rules with pack = "myproject"

   custom_rules_dir: .agentlint/rules/
   ```

   `universal` and `quality` are always active, so you do not need to list
   them. Remove one only with `exclude_packs`.

4. Check that it loaded:

   ```bash
   agentlint list-rules --pack myproject
   agentlint doctor
   ```

Rules whose `pack` is not in `packs:` are loaded but skipped. `agentlint doctor`
reports these orphaned packs.

## Rule anatomy

Every rule needs these class attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `str` | Unique identifier. Do not reuse a built-in rule ID ([rules.md](rules.md)). |
| `description` | `str` | One-line description, shown by `agentlint list-rules`. |
| `severity` | `Severity` | `ERROR` (blocks on `PreToolUse`), `WARNING` (advises), or `INFO` (reports). |
| `events` | `list[HookEvent]` | Events this rule runs on. |
| `pack` | `str` | Pack name, any string. It must be listed in `packs:` to activate. |

And one method:

```python
def evaluate(self, context: RuleContext) -> list[Violation]:
    """Return a list of violations. An empty list means pass."""
```

A `Violation` has `rule_id`, `message` and `severity`, plus optional
`file_path`, `line`, `suggestion` (shown as a correction to the agent),
`operation` and `policy_source`. A rule may return a severity different from
its class default for an individual violation.

The project `severity` setting (`strict` / `relaxed`) and the circuit breaker
apply to custom rules the same way as to built-in rules. If `evaluate()` raises
an exception, the error is logged and the rule is skipped for that call, unless
the rule is required (see below).

## A blocking rule

`ERROR` violations on `PreToolUse` deny the tool call. This rule blocks shell
commands that run migrations against the production database URL:

```python
# .agentlint/rules/no_prod_migrations.py
import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_MIGRATE = re.compile(r"\b(alembic\s+upgrade|manage\.py\s+migrate)\b")


class NoProdMigrations(Rule):
    id = "no-prod-migrations"
    description = "Block database migrations that target production"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "myproject"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        command = context.command or ""
        if _MIGRATE.search(command) and "PROD_DATABASE_URL" in command:
            return [
                Violation(
                    rule_id=self.id,
                    message="Migration targets the production database.",
                    severity=self.severity,
                    suggestion="Run migrations through the deploy pipeline instead.",
                )
            ]
        return []
```

`context.command` is `tool_input["command"]`. It is set for shell tools that
use that key (for example Claude Code's `Bash`).

## RuleContext fields

`evaluate()` receives a `RuleContext` (`src/agentlint/core/models.py`). Fields
that do not apply to the current event are `None`.

| Field | Type | Description |
|-------|------|-------------|
| `event` | `HookEvent` | Current lifecycle event. |
| `tool_name` | `str` | The agent's own tool name, e.g. `Bash`, `Write`, `Edit` for Claude Code. Use `normalized_tool` to match across agents. |
| `tool_input` | `dict` | Tool arguments as sent by the agent. |
| `project_dir` | `str` | Absolute project root. |
| `file_content` | `str \| None` | New content for `PreToolUse` writes (from `tool_input["content"]`), or the file on disk after `PostToolUse`. |
| `file_content_before` | `str \| None` | File content before the edit, cached at `PreToolUse` for `Write`/`Edit` and available on `PostToolUse`. |
| `config` | `dict` | The `rules:` mapping from `agentlint.yml`. Read your settings with `context.config.get(self.id, {})`. |
| `session_state` | `dict` | Mutable state persisted across calls in the same session. |
| `prompt` | `str \| None` | Prompt text (`UserPromptSubmit`). |
| `subagent_output` | `str \| None` | Subagent's last message (`SubagentStop`). |
| `notification_type` | `str \| None` | Notification type (`Notification`). |
| `compact_source` | `str \| None` | `manual` or `auto` (`PreCompact`). |
| `agent_transcript_path` | `str \| None` | Subagent JSONL transcript (`SubagentStop`). |
| `agent_type` | `str \| None` | Subagent type (`SubagentStart`/`SubagentStop`). |
| `agent_id` | `str \| None` | Subagent ID (`SubagentStart`/`SubagentStop`). |
| `agent_platform` | `str` | Adapter name: `claude`, `cursor`, `codex`, `gemini`, `continue`, `kimi`, `grok`, `openai`, `mcp`, `generic`, or `unknown`. |
| `working_directory` | `str \| None` | The tool's working directory when the agent reports one (Codex); may be below `project_dir`. |
| `tool_response` | `dict \| None` | Tool result on `PostToolUse`, when the agent sends one. |

Properties:

| Property | Type | Description |
|----------|------|-------------|
| `file_path` | `str \| None` | `tool_input["file_path"]`. |
| `relative_file_path` | `str \| None` | `file_path` relative to `project_dir`, for path matching. |
| `command` | `str \| None` | `tool_input["command"]`. |
| `normalized_tool` | `NormalizedTool` | Tool category (`SHELL`, `FILE_WRITE`, `FILE_EDIT`, `FILE_READ`, `SEARCH`, `WEB_FETCH`, `WEB_SEARCH`, `SUB_AGENT`, `NOTEBOOK`, `UNKNOWN`) mapped from `tool_name` for the current `agent_platform`. |

### Custom rules see the original input

For built-in operation guards, AgentLint splits shell commands into parsed
operations and drops display and read-only ones, so `grep "rm -rf" log` is not
treated as a deletion. Custom rules do not get this projection: `tool_input`
and `command` contain the original, unmodified command. Credential, file-write
and organization rules also see the original input. If your rule should ignore
quoted text or read-only commands, handle that in the rule.

## Events

Which events reach AgentLint depends on the agent and on the hooks its setup
installs; see the page for your agent (for example
[agents/claude.md](agents/claude.md)). Rules can target any `HookEvent`:

| Event | When | Can an ERROR block? |
|-------|------|---------------------|
| `HookEvent.PRE_TOOL_USE` | Before a tool call | Yes |
| `HookEvent.POST_TOOL_USE` | After a tool call | No, advisory |
| `HookEvent.POST_TOOL_USE_FAILURE` | After a tool call fails | No |
| `HookEvent.USER_PROMPT_SUBMIT` | When the user sends a prompt | No, advisory |
| `HookEvent.SUB_AGENT_START` | When a subagent starts | No, injects context |
| `HookEvent.SUB_AGENT_STOP` | When a subagent finishes | No, advisory |
| `HookEvent.NOTIFICATION` | On agent notifications | No |
| `HookEvent.PRE_COMPACT` | Before context compaction | No |
| `HookEvent.SESSION_START` | Session begins | No |
| `HookEvent.SESSION_END` | Session ends | No |
| `HookEvent.STOP` | Agent finishes a turn | No, report |
| `HookEvent.PERMISSION_REQUEST` | Permission prompt | No |
| `HookEvent.CONFIG_CHANGE` | Settings changed | No |
| `HookEvent.WORKTREE_CREATE` | Git worktree created | No |
| `HookEvent.WORKTREE_REMOVE` | Git worktree removed | No |
| `HookEvent.TEAMMATE_IDLE` | Teammate goes idle | No |
| `HookEvent.TASK_COMPLETED` | Background task completes | No |

For Claude Code, `agentlint setup claude` registers `PreToolUse`,
`PostToolUse`, `UserPromptSubmit`, `SubagentStart`, `SubagentStop`,
`Notification` and `Stop`. To use another event, add a hook entry for it that
runs `agentlint check --event <EventName>`.

## Rule configuration

Read per-rule settings from `context.config`:

```yaml
rules:
  no-direct-db:
    route_dirs: ["/routes/", "/api/"]
```

```python
route_dirs = context.config.get(self.id, {}).get("route_dirs", ["/routes/"])
```

`enabled: false`, `allow_paths` and `ignore_paths` under the rule's key work for
custom rules as for built-in ones. See [configuration.md](configuration.md).

## Required rules

A workspace policy can list rule IDs under `workspace.required_rules`. Required
rules cannot be disabled: `enabled: false`, global path exemptions, inline
ignore comments, severity relaxation and circuit-breaker degradation do not
remove their findings, and an exception inside a required rule produces a
blocking error. This applies to custom rule IDs too, as long as the rule's pack
is active. See [configuration.md](configuration.md).

Approvals (`agentlint approve`) only relax built-in rules mapped to an action
class; they do not apply to custom rules. See
[approvals-and-evidence.md](approvals-and-evidence.md).

## Session state

`context.session_state` is a dict persisted between calls in the same agent
session. Use a key prefix unique to your rule:

```python
def evaluate(self, context: RuleContext) -> list[Violation]:
    state = context.session_state
    state["no-direct-db.count"] = state.get("no-direct-db.count", 0) + 1
    return []
```

## Testing a rule

Load rules the same way AgentLint does, then call `evaluate()` with a
hand-built context:

```python
# tests/test_custom_rules.py
from pathlib import Path

from agentlint.models import HookEvent, RuleContext
from agentlint.packs import load_custom_rules

PROJECT = Path(__file__).resolve().parents[1]


def _rule(rule_id: str):
    rules = load_custom_rules(".agentlint/rules", str(PROJECT))
    return next(r for r in rules if r.id == rule_id)


def test_flags_direct_db_import():
    context = RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": "app/routes/users.py"},
        project_dir=str(PROJECT),
        file_content="from database import session\n",
    )
    violations = _rule("no-direct-db").evaluate(context)
    assert [v.rule_id for v in violations] == ["no-direct-db"]


def test_passes_repository_import():
    context = RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": "app/routes/users.py"},
        project_dir=str(PROJECT),
        file_content="from app.repositories import users\n",
    )
    assert _rule("no-direct-db").evaluate(context) == []
```

To try a rule end to end, pipe a payload into `agentlint check`:

```bash
echo '{"tool_name": "Bash", "tool_input": {"command": "PROD_DATABASE_URL=x alembic upgrade head"}}' \
  | agentlint check --event PreToolUse --adapter claude
```

## Rule discovery

- Every `.py` file directly in `custom_rules_dir` is loaded. Subdirectories are
  not scanned.
- Files starting with `_` (`_helpers.py`, `__init__.py`) are skipped. Use them
  for shared code.
- Each file may define several `Rule` subclasses. Every subclass with an `id`
  is instantiated with no arguments.
- `custom_rules_dir` is relative to the project root (or to the policy file
  that sets it, for workspace policies).
- A file that fails to import is logged and skipped; other rules still load.

### Distributing rules as a package

Rules can also be installed as a Python package through the `agentlint.rules`
entry-point group. Each entry point must be a callable that returns a `Rule` or
a list of rules. Installed rules are filtered by `packs:` like directory rules.

```toml
# pyproject.toml of your rules package
[project.entry-points."agentlint.rules"]
myproject = "myproject_rules:rules"
```

```python
# myproject_rules/__init__.py
from agentlint.models import Rule

from myproject_rules.no_direct_db import NoDirectDB


def rules() -> list[Rule]:
    return [NoDirectDB()]
```

## Debugging

If a rule does not run:

1. Run `agentlint list-rules --pack <pack>`. If the rule is missing, the file
   did not load.
2. Check that `custom_rules_dir` is relative to the project root and the file
   name does not start with `_`.
3. Check that the class subclasses `Rule` and sets `id`, `description`,
   `severity`, `events` and `pack`.
4. Check that `pack` is listed in `packs:`. `agentlint doctor` reports orphaned
   packs.
5. Run with debug logging to see import errors:
   `AGENTLINT_LOG_LEVEL=DEBUG agentlint list-rules`.
6. Capture a sanitized record of a real hook call with
   `agentlint check --diagnostic-bundle <file>`. See
   [diagnostics.md](diagnostics.md).
