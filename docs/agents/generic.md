# Generic integration

For an agent framework without a dedicated adapter, pipe a JSON description of each tool call to `agentlint check --adapter generic` and act on the JSON result, or call the rule engine from Python.

## Install

There is no hook file to write. Install AgentLint where your agent runs and create a policy file:

```bash
pip install agentlint
agentlint init          # writes agentlint.yml
```

## Verify

```bash
echo '{"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}}' \
  | agentlint check --adapter generic --event pre_tool_use --project-dir .
echo "exit=$?"
```

You should see `{"blocked": true, "violations": [...]}` and `exit=1`.

## What is checked

### Input

`agentlint check --adapter generic --event <event>` reads one JSON object from stdin:

| Field | Used for |
|-------|----------|
| `tool_name` | Tool being called. Use Claude-style names: `Bash`, `Write`, `Edit`. Built-in rules match these names exactly, so `file_write` or `shell` match no tool-specific rules. |
| `tool_input` | Tool arguments: `{"command": "..."}` for `Bash`; `{"file_path": "...", "content": "..."}` for `Write`/`Edit`. |
| `tool_response` | Optional, post-tool events: the tool result object. |
| `prompt` | Prompt text for `user_prompt`. |
| `subagent_output` or `last_assistant_message` | Subagent output for `sub_agent_stop`. |
| `notification_type`, `compact_source`, `agent_type`, `agent_id`, `agent_transcript_path` | Optional event context. |

`--event` takes AgentLint's normalized event names, either the value or the upper-case name: `pre_tool_use` / `PRE_TOOL_USE`, `post_tool_use`, `post_tool_failure`, `user_prompt`, `session_start`, `session_end`, `sub_agent_start`, `sub_agent_stop`, `notification`, `pre_compact`, `permission_request`, `config_change`, `worktree_create`, `worktree_remove`, `teammate_idle`, `task_completed`, `stop`.

### Output

- No findings: no output, exit 0.
- Findings: one JSON object on stdout.

  ```json
  {
    "blocked": true,
    "violations": [
      {
        "rule_id": "no-secrets",
        "message": "Possible secret token detected (prefix 'sk_live_')",
        "severity": "error",
        "file_path": "config.py",
        "line": null,
        "suggestion": "Use environment variables instead of hard-coded secrets.",
        "operation": "Write",
        "policy_source": "built-in universal pack; built-in defaults (no policy file)"
      }
    ]
  }
  ```

  `operation` and `policy_source` appear only when known.
- Exit 1 when any finding has `severity: "error"` (your integration should refuse the action); exit 0 for warnings and info only.
- Exit 2 with a message on stderr for an invalid `agentlint.yml`.

Each call updates the session state, recordings and (if enabled) the [AgentChute](../agentchute.md) queue, exactly like an agent hook. Run `agentlint report --adapter generic` at the end of a session for the summary.

## Python embedding

To evaluate in-process without a subprocess:

```python
from agentlint.config import load_config
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext
from agentlint.packs import load_project_rules

project_dir = "/path/to/project"
config = load_config(project_dir)
rules = load_project_rules(config, project_dir)
engine = Engine(config=config, rules=rules)

context = RuleContext(
    event=HookEvent.PRE_TOOL_USE,
    tool_name="Bash",
    tool_input={"command": "git push --force origin main"},
    project_dir=project_dir,
    config=config.rules,
)
result = engine.evaluate(context)

if result.is_blocking:
    for v in result.violations:
        print(v.to_dict())
```

This path does not record heartbeats, sessions or AgentChute events. Load the config and rules once and reuse the engine across calls.

## Configuration notes

- Project directory: `--project-dir`, then `AGENTLINT_PROJECT_DIR`, then `CLAUDE_PROJECT_DIR`, then the current directory.
- Session state key: `AGENTLINT_SESSION_ID`, otherwise the parent process ID. Set `AGENTLINT_SESSION_ID` to one value per agent session so session-scoped rules and suppressions work.
- `agentlint setup generic` writes nothing; it prints the `agentlint check` call to use.
- To ship a reusable integration for a new agent, see [Custom adapters](../custom-adapters.md).

## Uninstall

Remove the `agentlint check` call from your integration. `agentlint uninstall generic` is a no-op.

## Troubleshooting

- **Nothing is ever flagged:** check `tool_name`. Rules match `Bash`, `Write` and `Edit`, not normalized names.
- **`Unknown generic event`:** use one of the event names listed above.
- General issues: [Diagnostics](../diagnostics.md).
