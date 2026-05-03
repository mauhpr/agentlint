"""Tests for the MCP adapter."""
from __future__ import annotations

import pytest

from agentlint.adapters.mcp import MCPAdapter
from agentlint.models import AgentEvent, NormalizedTool


class TestEventTranslation:
    def test_tools_call_request(self) -> None:
        adapter = MCPAdapter()
        assert adapter.translate_event("tools/call/request") == AgentEvent.PRE_TOOL_USE

    def test_tools_call_response(self) -> None:
        adapter = MCPAdapter()
        assert adapter.translate_event("tools/call/response") == AgentEvent.POST_TOOL_USE

    def test_generic_event_fallback(self) -> None:
        adapter = MCPAdapter()
        assert adapter.translate_event("pre_tool_use") == AgentEvent.PRE_TOOL_USE

    def test_unknown_event_raises(self) -> None:
        adapter = MCPAdapter()
        with pytest.raises(ValueError, match="Unknown agent event"):
            adapter.translate_event("nonexistent")


class TestToolNormalization:
    def test_write(self) -> None:
        adapter = MCPAdapter()
        assert adapter.normalize_tool_name("write") == NormalizedTool.FILE_WRITE.value

    def test_mcp_prefixed(self) -> None:
        adapter = MCPAdapter()
        assert adapter.normalize_tool_name("MCP:shell") == NormalizedTool.SHELL.value

    def test_unknown(self) -> None:
        adapter = MCPAdapter()
        assert adapter.normalize_tool_name("custom") == NormalizedTool.UNKNOWN.value


class TestBuildRuleContext:
    def test_basic_context(self) -> None:
        adapter = MCPAdapter()
        context = adapter.build_rule_context(
            AgentEvent.PRE_TOOL_USE,
            {"tool_name": "Write", "tool_input": {"file_path": "test.py"}},
            "/project",
            {},
        )
        assert context.agent_platform == "mcp"
        assert context.tool_name == "Write"

    def test_arguments_alias(self) -> None:
        adapter = MCPAdapter()
        context = adapter.build_rule_context(
            AgentEvent.PRE_TOOL_USE,
            {"name": "bash", "arguments": {"command": "ls"}},
            "/project",
            {},
        )
        assert context.tool_input == {"command": "ls"}


class TestMCPAdapterServerMode:
    def test_list_rules_returns_rules(self, tmp_path) -> None:
        adapter = MCPAdapter()
        rules = adapter.list_rules()
        assert len(rules) > 0
        assert all("id" in r and "severity" in r for r in rules)

    def test_get_config_returns_dict(self, tmp_path) -> None:
        adapter = MCPAdapter()
        config = adapter.get_config()
        assert "severity" in config
        assert "packs" in config

    def test_check_content_detects_secrets(self, tmp_path) -> None:
        adapter = MCPAdapter()
        violations = adapter.check_content(
            content='API_KEY = "sk_live_abc123"',
            file_path=str(tmp_path / "config.py"),
            tool_name="Write",
            event="PreToolUse",
        )
        assert len(violations) > 0
        assert any(v["rule_id"] == "no-secrets" for v in violations)


class TestMCPAdapterMisc:
    def test_formatter_is_plain_json(self) -> None:
        adapter = MCPAdapter()
        formatter = adapter.formatter
        from agentlint.formats.plain_json import PlainJsonFormatter
        assert isinstance(formatter, PlainJsonFormatter)

    def test_resolve_project_dir_from_claude_env(self, monkeypatch) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", "/claude/project")
        adapter = MCPAdapter()
        assert adapter.resolve_project_dir() == "/claude/project"

    def test_resolve_session_key_from_mcp_env(self, monkeypatch) -> None:
        monkeypatch.setenv("MCP_SESSION_ID", "mcp-session-123")
        adapter = MCPAdapter()
        assert adapter.resolve_session_key() == "mcp-session-123"

    def test_install_hooks_prints_config(self, tmp_path) -> None:
        from unittest.mock import patch
        adapter = MCPAdapter()
        with patch("click.echo") as mock_echo:
            adapter.install_hooks(str(tmp_path))
        outputs = [str(call.args[0]) for call in mock_echo.call_args_list]
        combined = "\n".join(outputs)
        assert "mcpServers" in combined
        assert "agentlint" in combined

    def test_uninstall_hooks_noop(self, tmp_path) -> None:
        adapter = MCPAdapter()
        adapter.uninstall_hooks(str(tmp_path))  # should not raise

    def test_check_content_invalid_event_returns_error(self, tmp_path) -> None:
        adapter = MCPAdapter()
        violations = adapter.check_content(
            content="x = 1",
            file_path=str(tmp_path / "app.py"),
            event="NotAValidEvent",
        )
        assert len(violations) == 1
        assert "error" in violations[0]

    def test_check_content_monorepo_uses_project_packs(self, tmp_path) -> None:
        (tmp_path / "agentlint.yml").write_text(
            "packs:\n  - universal\n"
            "projects:\n  backend/:\n    packs: [universal, python]\n"
        )
        import os
        old = os.environ.get("CLAUDE_PROJECT_DIR")
        os.environ["CLAUDE_PROJECT_DIR"] = str(tmp_path)
        (tmp_path / "backend").mkdir()
        try:
            adapter = MCPAdapter()
            violations = adapter.check_content(
                content="try:\n    pass\nexcept:\n    pass\n",
                file_path=str(tmp_path / "backend" / "app.py"),
            )
            assert any(v.get("rule_id") == "no-bare-except" for v in violations)
        finally:
            if old is None:
                os.environ.pop("CLAUDE_PROJECT_DIR", None)
            else:
                os.environ["CLAUDE_PROJECT_DIR"] = old


class TestPlainJsonFormatter:
    def test_format_returns_none_when_empty(self) -> None:
        from agentlint.formats.plain_json import PlainJsonFormatter
        formatter = PlainJsonFormatter()
        assert formatter.format([]) is None

    def test_format_returns_json_with_violations(self) -> None:
        from agentlint.formats.plain_json import PlainJsonFormatter
        from agentlint.models import Severity, Violation
        formatter = PlainJsonFormatter()
        violations = [Violation(rule_id="test", message="msg", severity=Severity.WARNING)]
        output = formatter.format(violations)
        import json
        data = json.loads(output)
        assert data["blocked"] is False
        assert len(data["violations"]) == 1

    def test_format_blocked_with_errors(self) -> None:
        from agentlint.formats.plain_json import PlainJsonFormatter
        from agentlint.models import Severity, Violation
        formatter = PlainJsonFormatter()
        violations = [Violation(rule_id="test", message="msg", severity=Severity.ERROR)]
        output = formatter.format(violations)
        import json
        data = json.loads(output)
        assert data["blocked"] is True

    def test_exit_code_with_errors(self) -> None:
        from agentlint.formats.plain_json import PlainJsonFormatter
        from agentlint.models import Severity, Violation
        formatter = PlainJsonFormatter()
        violations = [Violation(rule_id="test", message="msg", severity=Severity.ERROR)]
        assert formatter.exit_code(violations) == 1

    def test_exit_code_without_errors(self) -> None:
        from agentlint.formats.plain_json import PlainJsonFormatter
        from agentlint.models import Severity, Violation
        formatter = PlainJsonFormatter()
        violations = [Violation(rule_id="test", message="msg", severity=Severity.WARNING)]
        assert formatter.exit_code(violations) == 0

    def test_format_subagent_start_delegates(self) -> None:
        from agentlint.formats.plain_json import PlainJsonFormatter
        from agentlint.models import Severity, Violation
        formatter = PlainJsonFormatter()
        violations = [Violation(rule_id="test", message="msg", severity=Severity.WARNING)]
        output = formatter.format_subagent_start(violations)
        import json
        data = json.loads(output)
        assert len(data["violations"]) == 1
