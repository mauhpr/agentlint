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
