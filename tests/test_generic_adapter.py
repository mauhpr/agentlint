"""Tests for the generic HTTP/webhook adapter."""
from __future__ import annotations

import pytest

from agentlint.adapters.generic import GenericAdapter
from agentlint.models import AgentEvent, NormalizedTool


class TestEventTranslation:
    def test_pre_tool_use_by_value(self) -> None:
        adapter = GenericAdapter()
        assert adapter.translate_event("pre_tool_use") == AgentEvent.PRE_TOOL_USE

    def test_pre_tool_use_by_name(self) -> None:
        adapter = GenericAdapter()
        assert adapter.translate_event("PRE_TOOL_USE") == AgentEvent.PRE_TOOL_USE

    def test_stop(self) -> None:
        adapter = GenericAdapter()
        assert adapter.translate_event("stop") == AgentEvent.STOP

    def test_unknown_event_raises(self) -> None:
        adapter = GenericAdapter()
        with pytest.raises(ValueError, match="Unknown generic event"):
            adapter.translate_event("nonexistent")


class TestToolNormalization:
    def test_known_tools(self) -> None:
        adapter = GenericAdapter()
        assert adapter.normalize_tool_name("file_write") == NormalizedTool.FILE_WRITE.value
        assert adapter.normalize_tool_name("shell") == NormalizedTool.SHELL.value
        assert adapter.normalize_tool_name("search") == NormalizedTool.SEARCH.value

    def test_unknown_tool(self) -> None:
        adapter = GenericAdapter()
        assert adapter.normalize_tool_name("custom_tool") == NormalizedTool.UNKNOWN.value


class TestBuildRuleContext:
    def test_basic_context(self) -> None:
        adapter = GenericAdapter()
        context = adapter.build_rule_context(
            AgentEvent.PRE_TOOL_USE,
            {"tool_name": "file_write", "tool_input": {"file_path": "test.py"}},
            "/project",
            {},
        )
        assert context.agent_platform == "generic"
        assert context.tool_name == "file_write"

    def test_resolves_project_dir_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENTLINT_PROJECT_DIR", "/my/project")
        adapter = GenericAdapter()
        assert adapter.resolve_project_dir() == "/my/project"


class TestGenericAdapterMisc:
    def test_formatter_is_plain_json(self) -> None:
        adapter = GenericAdapter()
        from agentlint.formats.plain_json import PlainJsonFormatter
        assert isinstance(adapter.formatter, PlainJsonFormatter)

    def test_install_hooks_prints_example(self, tmp_path) -> None:
        from unittest.mock import patch
        adapter = GenericAdapter()
        with patch("click.echo") as mock_echo:
            adapter.install_hooks(str(tmp_path))
        outputs = [str(call.args[0]) for call in mock_echo.call_args_list]
        combined = "\n".join(outputs)
        assert "Generic adapter configured" in combined

    def test_uninstall_hooks_noop(self, tmp_path) -> None:
        adapter = GenericAdapter()
        adapter.uninstall_hooks(str(tmp_path))  # should not raise
