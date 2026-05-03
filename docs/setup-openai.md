# Setup Guide: OpenAI Agents SDK

AgentLint integrates with OpenAI Agents SDK via guardrails.

## Installation

OpenAI Agents SDK uses code-based guardrails, not file-based hooks:

```bash
agentlint setup openai
```

This prints a setup code snippet:

```python
from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
from openai.agents import Agent

adapter = OpenAIAgentsAdapter()
agent = Agent(
    name="my-agent",
    tools=[...],
    guardrails=[adapter.as_guardrail()],
)
```

## Guardrail Integration

The adapter provides `evaluate_tool_call()` which returns a guardrail-compatible dict:

```python
result = adapter.evaluate_tool_call(
    tool_name="file_write",
    tool_input={"file_path": "config.py", "content": "..."},
)

# result = {
#     "tripwire_triggered": True/False,
#     "violations": [...],
#     "blocked_count": 0,
#     "warning_count": 0,
# }
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_RUN_ID` | Run ID for session tracking |
| `OPENAI_THREAD_ID` | Thread ID for session tracking |
| `AGENTLINT_PROJECT_DIR` | Project directory |
| `AGENTLINT_SESSION_ID` | Generic session ID |
