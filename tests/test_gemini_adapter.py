"""Tests for the Gemini CLI adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlint.adapters.gemini import GeminiAdapter, _build_hooks, _settings_path
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext


class TestEventTranslation:
    def test_before_tool(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.translate_event("BeforeTool") == AgentEvent.PRE_TOOL_USE

    def test_after_tool(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.translate_event("AfterTool") == AgentEvent.POST_TOOL_USE

    def test_before_agent(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.translate_event("BeforeAgent") == AgentEvent.USER_PROMPT

    def test_after_agent(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.translate_event("AfterAgent") == AgentEvent.STOP

    def test_session_start(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.translate_event("SessionStart") == AgentEvent.SESSION_START

    def test_pre_compress(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.translate_event("PreCompress") == AgentEvent.PRE_COMPACT

    def test_unknown_event_raises(self) -> None:
        adapter = GeminiAdapter()
        with pytest.raises(ValueError, match="Unknown Gemini event"):
            adapter.translate_event("unknownEvent")


class TestToolNormalization:
    def test_bash(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.normalize_tool_name("bash") == NormalizedTool.SHELL.value

    def test_write_file(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.normalize_tool_name("write_file") == NormalizedTool.FILE_WRITE.value

    def test_replace(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.normalize_tool_name("replace") == NormalizedTool.FILE_EDIT.value

    def test_read_file(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.normalize_tool_name("read_file") == NormalizedTool.FILE_READ.value

    def test_unknown(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.normalize_tool_name("unknown") == NormalizedTool.UNKNOWN.value


class TestBuildRuleContext:
    def test_basic_context(self) -> None:
        adapter = GeminiAdapter()
        context = adapter.build_rule_context(
            AgentEvent.PRE_TOOL_USE,
            {"tool_name": "write_file", "tool_input": {"file_path": "test.py"}},
            "/project",
            {},
        )
        assert context.event == HookEvent.PRE_TOOL_USE
        assert context.tool_name == "write_file"
        assert context.agent_platform == "gemini"

    def test_resolves_project_dir_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("GEMINI_PROJECT_DIR", "/my/gemini/project")
        adapter = GeminiAdapter()
        assert adapter.resolve_project_dir() == "/my/gemini/project"

    def test_formatter_property(self) -> None:
        from agentlint.formats.gemini_hooks import GeminiHookFormatter
        adapter = GeminiAdapter()
        assert isinstance(adapter.formatter, GeminiHookFormatter)

    def test_resolves_project_dir_from_agentlint_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENTLINT_PROJECT_DIR", "/my/agentlint/project")
        adapter = GeminiAdapter()
        assert adapter.resolve_project_dir() == "/my/agentlint/project"

    def test_resolves_session_key_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENTLINT_SESSION_ID", "session-123")
        adapter = GeminiAdapter()
        assert adapter.resolve_session_key() == "session-123"

    def test_normalize_unknown_tool(self) -> None:
        adapter = GeminiAdapter()
        assert adapter.normalize_tool_name("unknown_tool") == "unknown"


class TestSettingsPath:
    def test_project_scope(self, tmp_path) -> None:
        path = _settings_path("project", str(tmp_path))
        assert path == tmp_path / ".gemini" / "settings.json"

    def test_user_scope(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        path = _settings_path("user")
        assert path == tmp_path / ".gemini" / "settings.json"


class TestBuildHooks:
    EXPECTED_EVENTS = {
        "BeforeTool", "AfterTool", "BeforeAgent", "AfterAgent",
        "SessionStart", "PreCompress",
    }

    def test_builds_all_events(self) -> None:
        hooks = _build_hooks("agentlint")
        assert set(hooks["hooks"].keys()) == self.EXPECTED_EVENTS

    def test_embeds_adapter_flag(self) -> None:
        hooks = _build_hooks("agentlint")
        pre_cmd = hooks["hooks"]["BeforeTool"][0]["hooks"][0]["command"]
        assert "--adapter gemini" in pre_cmd


class TestInstallHooks:
    def test_creates_settings_json(self, tmp_path) -> None:
        adapter = GeminiAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        settings_file = tmp_path / ".gemini" / "settings.json"
        assert settings_file.exists()
        data = json.loads(settings_file.read_text())
        assert "hooks" in data
        assert set(data["hooks"].keys()) == TestBuildHooks.EXPECTED_EVENTS

    def test_idempotent_install(self, tmp_path) -> None:
        adapter = GeminiAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        first = (tmp_path / ".gemini" / "settings.json").read_text()

        adapter.install_hooks(str(tmp_path), scope="project")
        second = (tmp_path / ".gemini" / "settings.json").read_text()

        assert first == second

    def test_preserves_existing_hooks(self, tmp_path) -> None:
        settings_file = tmp_path / ".gemini" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        existing = {
            "hooks": {
                "BeforeTool": [
                    {"matcher": "write_file", "hooks": [{"name": "my-hook", "type": "command", "command": "echo hello"}]}
                ]
            }
        }
        settings_file.write_text(json.dumps(existing))

        adapter = GeminiAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        data = json.loads(settings_file.read_text())
        before_tool = data["hooks"]["BeforeTool"]
        assert len(before_tool) == 2
        assert before_tool[0]["hooks"][0]["command"] == "echo hello"
        assert "agentlint" in before_tool[1]["hooks"][0]["command"]

    def test_dry_run_does_not_write(self, tmp_path) -> None:
        adapter = GeminiAdapter()
        adapter.install_hooks(str(tmp_path), scope="project", dry_run=True)

        settings_file = tmp_path / ".gemini" / "settings.json"
        assert not settings_file.exists()


class TestUninstallHooks:
    def test_removes_hooks(self, tmp_path) -> None:
        adapter = GeminiAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        settings_file = tmp_path / ".gemini" / "settings.json"
        assert not settings_file.exists()

    def test_preserves_other_hooks(self, tmp_path) -> None:
        settings_file = tmp_path / ".gemini" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        existing = {
            "hooks": {
                "BeforeTool": [
                    {"matcher": "write_file", "hooks": [{"name": "my-hook", "type": "command", "command": "echo hello"}]},
                    {"matcher": "write_file", "hooks": [{"name": "agentlint-pre", "type": "command", "command": "agentlint check --event BeforeTool --adapter gemini"}]},
                ]
            }
        }
        settings_file.write_text(json.dumps(existing))

        adapter = GeminiAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        data = json.loads(settings_file.read_text())
        assert len(data["hooks"]["BeforeTool"]) == 1
        assert data["hooks"]["BeforeTool"][0]["hooks"][0]["command"] == "echo hello"

    def test_uninstall_aborts_on_corrupted_file(self, tmp_path) -> None:
        settings_file = tmp_path / ".gemini" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text("not json")

        adapter = GeminiAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        assert settings_file.read_text() == "not json"


class TestFormatter:
    def test_blocking_format(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.gemini_hooks import GeminiHookFormatter

        formatter = GeminiHookFormatter()
        violations = [Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR)]
        output = formatter.format(violations, AgentEvent.PRE_TOOL_USE)
        assert output is not None
        data = json.loads(output)
        assert data["decision"] == "deny"
        assert "reason" in data

    def test_advisory_format(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.gemini_hooks import GeminiHookFormatter

        formatter = GeminiHookFormatter()
        violations = [Violation(rule_id="max-file-size", message="File too large", severity=Severity.WARNING)]
        output = formatter.format(violations, AgentEvent.POST_TOOL_USE)
        assert output is not None
        data = json.loads(output)
        assert "hookSpecificOutput" in data
        assert "additionalContext" in data["hookSpecificOutput"]

    def test_exit_code_blocked(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.gemini_hooks import GeminiHookFormatter

        formatter = GeminiHookFormatter()
        violations = [Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR)]
        assert formatter.exit_code(violations, AgentEvent.PRE_TOOL_USE) == 2

    def test_exit_code_allowed(self) -> None:
        from agentlint.formats.gemini_hooks import GeminiHookFormatter

        formatter = GeminiHookFormatter()
        assert formatter.exit_code([], AgentEvent.PRE_TOOL_USE) == 0


class TestFormatterEdgeCases:
    def test_format_returns_none_when_no_violations(self) -> None:
        from agentlint.formats.gemini_hooks import GeminiHookFormatter
        formatter = GeminiHookFormatter()
        assert formatter.format([], AgentEvent.PRE_TOOL_USE) is None

    def test_format_fallback_for_other_events(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.gemini_hooks import GeminiHookFormatter

        formatter = GeminiHookFormatter()
        violations = [Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR)]
        output = formatter.format(violations, AgentEvent.STOP)
        assert output is not None
        data = json.loads(output)
        assert "hookSpecificOutput" in data
        assert "additionalContext" in data["hookSpecificOutput"]

    def test_format_subagent_start(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.gemini_hooks import GeminiHookFormatter

        formatter = GeminiHookFormatter()
        violations = [Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR)]
        output = formatter.format_subagent_start(violations)
        assert output is not None
        data = json.loads(output)
        assert data["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
        assert "Secret found" in data["hookSpecificOutput"]["additionalContext"]

    def test_format_subagent_start_returns_none(self) -> None:
        from agentlint.formats.gemini_hooks import GeminiHookFormatter

        formatter = GeminiHookFormatter()
        assert formatter.format_subagent_start([]) is None
