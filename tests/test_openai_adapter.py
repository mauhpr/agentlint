"""Tests for the OpenAI Agents SDK adapter."""
from __future__ import annotations

import pytest

from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
from agentlint.models import AgentEvent, NormalizedTool


class TestEventTranslation:
    def test_before_tool_call(self) -> None:
        adapter = OpenAIAgentsAdapter()
        assert adapter.translate_event("beforeToolCall") == AgentEvent.PRE_TOOL_USE

    def test_after_tool_call(self) -> None:
        adapter = OpenAIAgentsAdapter()
        assert adapter.translate_event("afterToolCall") == AgentEvent.POST_TOOL_USE

    def test_on_handoff(self) -> None:
        adapter = OpenAIAgentsAdapter()
        assert adapter.translate_event("onHandoff") == AgentEvent.SUB_AGENT_START

    def test_on_complete(self) -> None:
        adapter = OpenAIAgentsAdapter()
        assert adapter.translate_event("onComplete") == AgentEvent.SESSION_END

    def test_unknown_event_raises(self) -> None:
        adapter = OpenAIAgentsAdapter()
        with pytest.raises(ValueError, match="Unknown OpenAI Agents event"):
            adapter.translate_event("unknownEvent")


class TestToolNormalization:
    def test_shell(self) -> None:
        adapter = OpenAIAgentsAdapter()
        assert adapter.normalize_tool_name("shell") == NormalizedTool.SHELL.value

    def test_file_write(self) -> None:
        adapter = OpenAIAgentsAdapter()
        assert adapter.normalize_tool_name("file_write") == NormalizedTool.FILE_WRITE.value

    def test_unknown(self) -> None:
        adapter = OpenAIAgentsAdapter()
        assert adapter.normalize_tool_name("unknown_tool") == NormalizedTool.UNKNOWN.value


class TestEvaluateToolCall:
    def test_blocks_secrets(self, tmp_path) -> None:
        adapter = OpenAIAgentsAdapter()
        # Use "Write" as tool_name so existing rules recognize it
        result = adapter.evaluate_tool_call(
            "Write",
            {"file_path": str(tmp_path / "config.py"), "content": 'API_KEY = "sk_live_abc123"'},
            project_dir=str(tmp_path),
        )
        assert result["tripwire_triggered"] is True
        assert result["blocked_count"] > 0
        assert any(v["rule_id"] == "no-secrets" for v in result["violations"])

    def test_passes_clean_code(self, tmp_path) -> None:
        adapter = OpenAIAgentsAdapter()
        result = adapter.evaluate_tool_call(
            "Write",
            {"file_path": str(tmp_path / "hello.py"), "content": "def hello(): return 'world'\n"},
            project_dir=str(tmp_path),
        )
        assert result["tripwire_triggered"] is False
        assert result["blocked_count"] == 0

    def test_guardrail_dict(self) -> None:
        adapter = OpenAIAgentsAdapter()
        guardrail = adapter.as_guardrail()
        assert guardrail["name"] == "agentlint"
        assert guardrail["type"] == "tool"
        assert callable(guardrail["handler"])


class TestOpenAIAdapterMisc:
    def test_formatter_is_plain_json(self) -> None:
        from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
        from agentlint.formats.plain_json import PlainJsonFormatter
        adapter = OpenAIAgentsAdapter()
        assert isinstance(adapter.formatter, PlainJsonFormatter)

    def test_resolve_project_dir_from_openai_env(self, monkeypatch) -> None:
        from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
        monkeypatch.setenv("OPENAI_PROJECT_DIR", "/openai/project")
        adapter = OpenAIAgentsAdapter()
        assert adapter.resolve_project_dir() == "/openai/project"

    def test_resolve_session_key_from_run_id(self, monkeypatch) -> None:
        from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
        monkeypatch.setenv("OPENAI_RUN_ID", "run-123")
        adapter = OpenAIAgentsAdapter()
        assert adapter.resolve_session_key() == "run-123"

    def test_resolve_session_key_from_thread_id(self, monkeypatch) -> None:
        from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
        monkeypatch.setenv("OPENAI_THREAD_ID", "thread-456")
        adapter = OpenAIAgentsAdapter()
        assert adapter.resolve_session_key() == "thread-456"

    def test_build_rule_context_with_arguments_fallback(self) -> None:
        from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
        from agentlint.models import AgentEvent, HookEvent
        adapter = OpenAIAgentsAdapter()
        context = adapter.build_rule_context(
            AgentEvent.PRE_TOOL_USE,
            {"arguments": {"file_path": "test.py"}, "function_name": "my_func"},
            "/project",
            {},
        )
        assert context.tool_input == {"file_path": "test.py"}
        assert context.tool_name == "my_func"
        assert context.event == HookEvent.PRE_TOOL_USE

    def test_install_hooks_prints_snippet(self, tmp_path) -> None:
        from unittest.mock import patch
        from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
        adapter = OpenAIAgentsAdapter()
        with patch("click.echo") as mock_echo:
            adapter.install_hooks(str(tmp_path))
        outputs = [str(call.args[0]) for call in mock_echo.call_args_list]
        combined = "\n".join(outputs)
        assert "guardrail" in combined.lower()

    def test_evaluate_tool_call_detects_secrets(self, tmp_path) -> None:
        from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
        adapter = OpenAIAgentsAdapter()
        result = adapter.evaluate_tool_call(
            tool_name="Write",
            tool_input={"file_path": "config.py", "content": 'API_KEY = "sk_live_abc"'},
            project_dir=str(tmp_path),
        )
        assert result["tripwire_triggered"] is True
        assert any("no-secrets" in v["rule_id"] for v in result["violations"])

    def test_evaluate_tool_call_with_custom_rules_dir(self, tmp_path) -> None:
        from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
        adapter = OpenAIAgentsAdapter()
        # Create agentlint.yml with custom_rules_dir pointing to non-existent path
        yml = tmp_path / "agentlint.yml"
        yml.write_text("custom_rules_dir: ./custom_rules\n")
        result = adapter.evaluate_tool_call(
            tool_name="Write",
            tool_input={"file_path": "config.py", "content": "x = 1"},
            project_dir=str(tmp_path),
        )
        assert result["tripwire_triggered"] is False
        assert result["violations"] == []

    def test_uninstall_hooks_noop(self, tmp_path) -> None:
        from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
        adapter = OpenAIAgentsAdapter()
        adapter.uninstall_hooks(str(tmp_path))  # should not raise
