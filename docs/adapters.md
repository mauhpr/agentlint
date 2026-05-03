# Writing Custom Adapters

AgentLint's adapter architecture lets you add support for any agent framework.

## Adapter Protocol

Create a class that inherits from `AgentAdapter`:

```python
from agentlint.adapters.base import AgentAdapter
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext

class MyFrameworkAdapter(AgentAdapter):
    @property
    def platform_name(self) -> str:
        return "myframework"

    @property
    def formatter(self):
        from agentlint.formats.plain_json import PlainJsonFormatter
        return PlainJsonFormatter()

    def resolve_project_dir(self) -> str:
        return os.environ.get("MYFRAMEWORK_PROJECT_DIR", os.getcwd())

    def resolve_session_key(self) -> str:
        return os.environ.get("MYFRAMEWORK_SESSION_ID", f"pid-{os.getppid()}")

    def translate_event(self, native_event: str) -> AgentEvent:
        mapping = {
            "beforeAction": AgentEvent.PRE_TOOL_USE,
            "afterAction": AgentEvent.POST_TOOL_USE,
        }
        return mapping[native_event]

    def normalize_tool_name(self, native_tool: str) -> str:
        mapping = {
            "write": NormalizedTool.FILE_WRITE,
            "bash": NormalizedTool.SHELL,
        }
        return mapping.get(native_tool, NormalizedTool.UNKNOWN).value

    def build_rule_context(self, event, raw_payload, project_dir, session_state):
        return RuleContext(
            event=HookEvent.PRE_TOOL_USE,  # or translate
            tool_name=raw_payload.get("tool_name", ""),
            tool_input=raw_payload.get("tool_input", {}),
            project_dir=project_dir,
            config={},
            session_state=session_state,
            agent_platform="myframework",
        )

    def install_hooks(self, project_dir, scope="project", dry_run=False, cmd=None):
        # Framework-specific installation logic
        pass

    def uninstall_hooks(self, project_dir, scope="project"):
        # Framework-specific uninstall logic
        pass
```

## Registering the Adapter

Add it to the CLI's `_resolve_adapter()` function in `src/agentlint/cli.py`:

```python
_ADAPTERS = {
    "claude": ClaudeAdapter,
    "cursor": CursorAdapter,
    "openai": OpenAIAgentsAdapter,
    "mcp": MCPAdapter,
    "generic": GenericAdapter,
    "myframework": MyFrameworkAdapter,  # <-- add here
}
```

## Output Formatters

You can also write custom formatters:

```python
from agentlint.formats.base import OutputFormatter
from agentlint.models import AgentEvent, Severity, Violation

class MyFormatter(OutputFormatter):
    def exit_code(self, violations, event=""):
        return 1 if any(v.severity == Severity.ERROR for v in violations) else 0

    def format(self, violations, event=""):
        return json.dumps({"issues": [v.to_dict() for v in violations]})
```

## Testing

Add tests in `tests/test_myframework_adapter.py` following the patterns in `tests/test_cursor_adapter.py`.
