# OpenAI Agents SDK

The OpenAI Agents SDK has no hook files. You call AgentLint from a tool input guardrail in your own code, using `OpenAIAgentsAdapter.evaluate_tool_call()`.

## Install

```bash
pip install agentlint openai-agents
agentlint init          # writes agentlint.yml
```

`agentlint setup openai` writes no files; it prints the snippet below.

Attach AgentLint to each function tool with a tool input guardrail:

```python
from agents import Agent, Runner
from agents.decorators import tool

from agentlint.adapters.openai_agents import OpenAIAgentsAdapter

agentlint = OpenAIAgentsAdapter()


@tool(tool_input_guardrails=[agentlint.tool_input_guardrail("Bash")])
def run_shell(command: str) -> str:
    """Run a shell command in the project."""
    ...


@tool(
    tool_input_guardrails=[
        agentlint.tool_input_guardrail("Write", arguments={"file_path": "path", "content": "text"})
    ]
)
def write_file(path: str, text: str) -> str:
    """Write a file in the project."""
    ...


agent = Agent(name="builder", tools=[run_shell, write_file])
result = Runner.run_sync(agent, "List the files in the repo")
```

`tool_input_guardrail(tool_name, arguments=None, project_dir=None)` takes what
the tool does in AgentLint terms (`Bash`, `Write` or `Edit`) and, if your tool's
argument names differ, a mapping from AgentLint's keys (`command`, `file_path`,
`content`, `old_string`, `new_string`) to yours. On an ERROR the SDK skips the
call and returns the AgentLint reasons to the model
(`ToolGuardrailFunctionOutput.reject_content`); otherwise the call proceeds.

To write the guardrail yourself, call `agentlint.evaluate_tool_call(...)` inside
your own `@tool_input_guardrail` function. Guardrail APIs belong to the SDK; see
its [guardrails documentation](https://openai.github.io/openai-agents-python/guardrails/).
`as_guardrail()` from earlier versions returned a plain dict the SDK can't use
and is deprecated.

`reject_content` skips the tool call and returns the AgentLint reasons to the model instead. Guardrail APIs belong to the SDK; check its [guardrails documentation](https://openai.github.io/openai-agents-python/guardrails/) for your installed version.

## Verify

Call the adapter directly:

```bash
python -c 'from agentlint.adapters.openai_agents import OpenAIAgentsAdapter as A; print(A().evaluate_tool_call("Bash", {"command": "rm -rf /"}))'
```

`tripwire_triggered` should be `True`. `agentlint status` does not cover this integration; it only reports hook-based agents.

## What is checked

`evaluate_tool_call(tool_name, tool_input, project_dir=None)` evaluates one call as a `PreToolUse` event with the project's `agentlint.yml` and returns:

```python
{
    "tripwire_triggered": bool,  # True if any finding is an ERROR
    "violations": [...],  # rule_id, message, severity, file_path, line, suggestion, ...
    "blocked_count": int,
    "warning_count": int,
}
```

Map each tool to the Claude-style name and argument shape that AgentLint rules expect:

| Your tool does | `tool_name` | `tool_input` |
|----------------|-------------|--------------|
| Runs a shell command | `Bash` | `{"command": "..."}` |
| Writes a file | `Write` | `{"file_path": "...", "content": "..."}` |
| Edits a file | `Edit` | `{"file_path": "...", "content": "..."}` |

The adapter's own names `shell`, `file_write` and `file_edit` are translated to these; any other name matches no tool-specific rules.

Tool guardrails only run for function tools and local MCP server tools. Hosted tools and the SDK's built-in shell and apply-patch tools do not go through this pipeline, so AgentLint cannot see those calls.

## Configuration notes

- Project directory: the `project_dir` argument, then `AGENTLINT_PROJECT_DIR`, then `OPENAI_PROJECT_DIR`, then the current directory.
- `evaluate_tool_call` loads config and rules on every call and does not keep session state, record events or upload to [AgentChute](../agentchute.md).
- For a lower-level API, see the Python embedding example in [Generic integration](generic.md#python-embedding).

## Uninstall

Remove the guardrail from your tools. `agentlint uninstall openai` is a no-op.

## Troubleshooting

- **Guardrail never trips:** check that you pass `Bash`, `Write` or `Edit` as `tool_name` with the argument names above.
- **`ModuleNotFoundError: openai.agents`:** import from `agents`, not `openai.agents`.
- General issues: [Diagnostics](../diagnostics.md).
