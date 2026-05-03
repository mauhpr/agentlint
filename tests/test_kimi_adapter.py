"""Tests for the Kimi Code CLI adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlint.adapters.kimi import KimiAdapter, _build_hooks, _config_path
from agentlint.adapters._utils import is_agentlint_flat_entry
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext


class TestEventTranslation:
    def test_pre_tool_use(self) -> None:
        adapter = KimiAdapter()
        assert adapter.translate_event("PreToolUse") == AgentEvent.PRE_TOOL_USE

    def test_post_tool_use(self) -> None:
        adapter = KimiAdapter()
        assert adapter.translate_event("PostToolUse") == AgentEvent.POST_TOOL_USE

    def test_stop(self) -> None:
        adapter = KimiAdapter()
        assert adapter.translate_event("Stop") == AgentEvent.STOP

    def test_session_start(self) -> None:
        adapter = KimiAdapter()
        assert adapter.translate_event("SessionStart") == AgentEvent.SESSION_START

    def test_notification(self) -> None:
        adapter = KimiAdapter()
        assert adapter.translate_event("Notification") == AgentEvent.NOTIFICATION

    def test_unknown_event_raises(self) -> None:
        adapter = KimiAdapter()
        with pytest.raises(ValueError, match="Unknown Kimi event"):
            adapter.translate_event("unknownEvent")


class TestToolNormalization:
    def test_shell(self) -> None:
        adapter = KimiAdapter()
        assert adapter.normalize_tool_name("Shell") == NormalizedTool.SHELL.value

    def test_write_file(self) -> None:
        adapter = KimiAdapter()
        assert adapter.normalize_tool_name("WriteFile") == NormalizedTool.FILE_WRITE.value

    def test_str_replace_file(self) -> None:
        adapter = KimiAdapter()
        assert adapter.normalize_tool_name("StrReplaceFile") == NormalizedTool.FILE_EDIT.value

    def test_read_file(self) -> None:
        adapter = KimiAdapter()
        assert adapter.normalize_tool_name("ReadFile") == NormalizedTool.FILE_READ.value

    def test_task(self) -> None:
        adapter = KimiAdapter()
        assert adapter.normalize_tool_name("Task") == NormalizedTool.SUB_AGENT.value

    def test_unknown(self) -> None:
        adapter = KimiAdapter()
        assert adapter.normalize_tool_name("UnknownTool") == NormalizedTool.UNKNOWN.value


class TestBuildRuleContext:
    def test_basic_context(self) -> None:
        adapter = KimiAdapter()
        context = adapter.build_rule_context(
            AgentEvent.PRE_TOOL_USE,
            {"tool_name": "WriteFile", "tool_input": {"file_path": "test.py"}},
            "/project",
            {},
        )
        assert context.event == HookEvent.PRE_TOOL_USE
        assert context.tool_name == "WriteFile"
        assert context.project_dir == "/project"
        assert context.agent_platform == "kimi"

    def test_resolves_project_dir_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("KIMI_PROJECT_DIR", "/my/kimi/project")
        adapter = KimiAdapter()
        assert adapter.resolve_project_dir() == "/my/kimi/project"

    def test_resolves_session_key_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("KIMI_SESSION_ID", "kimi-session-123")
        adapter = KimiAdapter()
        assert adapter.resolve_session_key() == "kimi-session-123"


class TestConfigPath:
    def test_project_scope(self, tmp_path) -> None:
        path = _config_path("project", str(tmp_path))
        assert path == tmp_path / ".kimi" / "config.toml"

    def test_user_scope(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        path = _config_path("user")
        assert path == tmp_path / ".kimi" / "config.toml"


class TestIsAgentlintEntry:
    def test_identifies_agentlint_entry(self) -> None:
        entry = {"command": "agentlint check --event PreToolUse --adapter kimi"}
        assert is_agentlint_flat_entry(entry) is True

    def test_rejects_third_party_entry(self) -> None:
        entry = {"command": "my-other-tool check"}
        assert is_agentlint_flat_entry(entry) is False


class TestBuildHooks:
    def test_builds_all_events(self) -> None:
        hooks = _build_hooks("agentlint")
        events = {h["event"] for h in hooks}
        assert events == {
            "PreToolUse", "PostToolUse", "UserPromptSubmit",
            "SubagentStart", "SubagentStop", "Notification", "Stop",
        }

    def test_embeds_adapter_flag(self) -> None:
        hooks = _build_hooks("agentlint")
        pre_cmd = hooks[0]["command"]
        assert "--adapter kimi" in pre_cmd


class TestInstallHooks:
    def test_creates_config_toml(self, tmp_path) -> None:
        adapter = KimiAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        config_file = tmp_path / ".kimi" / "config.toml"
        assert config_file.exists()
        text = config_file.read_text()
        assert "[[hooks]]" in text
        assert "event = \"PreToolUse\"" in text

    def test_idempotent_install(self, tmp_path) -> None:
        adapter = KimiAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        first = (tmp_path / ".kimi" / "config.toml").read_text()

        adapter.install_hooks(str(tmp_path), scope="project")
        second = (tmp_path / ".kimi" / "config.toml").read_text()

        assert first == second

    def test_preserves_existing_hooks(self, tmp_path) -> None:
        config_file = tmp_path / ".kimi" / "config.toml"
        config_file.parent.mkdir(parents=True)
        existing = "[[hooks]]\nevent = \"PostToolUse\"\ncommand = \"prettier --write\"\n"
        config_file.write_text(existing)

        adapter = KimiAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        text = config_file.read_text()
        assert "prettier --write" in text
        assert "agentlint" in text

    def test_dry_run_does_not_write(self, tmp_path) -> None:
        adapter = KimiAdapter()
        adapter.install_hooks(str(tmp_path), scope="project", dry_run=True)

        config_file = tmp_path / ".kimi" / "config.toml"
        assert not config_file.exists()


class TestUninstallHooks:
    def test_removes_hooks(self, tmp_path) -> None:
        adapter = KimiAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        config_file = tmp_path / ".kimi" / "config.toml"
        assert not config_file.exists()

    def test_preserves_other_hooks(self, tmp_path) -> None:
        config_file = tmp_path / ".kimi" / "config.toml"
        config_file.parent.mkdir(parents=True)
        existing = "[[hooks]]\nevent = \"PostToolUse\"\ncommand = \"prettier --write\"\n"
        config_file.write_text(existing)

        adapter = KimiAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        text = config_file.read_text()
        assert "prettier --write" in text
        assert "agentlint" not in text


class TestFormatter:
    def test_exit_code_blocked(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.claude_hooks import ClaudeHookFormatter

        formatter = ClaudeHookFormatter()
        violations = [Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR)]
        assert formatter.exit_code(violations, AgentEvent.PRE_TOOL_USE) == 0

    def test_exit_code_allowed(self) -> None:
        from agentlint.formats.claude_hooks import ClaudeHookFormatter

        formatter = ClaudeHookFormatter()
        assert formatter.exit_code([], AgentEvent.PRE_TOOL_USE) == 0

    def test_blocking_format(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.claude_hooks import ClaudeHookFormatter

        formatter = ClaudeHookFormatter()
        violations = [Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR)]
        output = formatter.format(violations, AgentEvent.PRE_TOOL_USE)
        assert output is not None
        data = json.loads(output)
        assert data["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_format_with_warnings_and_infos(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.claude_hooks import ClaudeHookFormatter

        formatter = ClaudeHookFormatter()
        violations = [
            Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR, suggestion="Use env vars"),
            Violation(rule_id="max-file-size", message="File too large", severity=Severity.WARNING, suggestion="Split it"),
            Violation(rule_id="todo", message="TODO found", severity=Severity.INFO, suggestion="Fix it"),
        ]
        output = formatter.format(violations, AgentEvent.STOP)
        assert output is not None
        data = json.loads(output)
        msg = data["systemMessage"]
        assert "BLOCKED" in msg
        assert "WARNINGS" in msg
        assert "INFO" in msg
        assert "Use env vars" in msg
        assert "Split it" in msg
        assert "Fix it" in msg

    def test_format_subagent_start(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.claude_hooks import ClaudeHookFormatter

        formatter = ClaudeHookFormatter()
        violations = [Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR)]
        output = formatter.format_subagent_start(violations)
        assert output is not None
        data = json.loads(output)
        assert data["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
        assert "Secret found" in data["hookSpecificOutput"]["additionalContext"]

    def test_format_subagent_start_returns_none(self) -> None:
        from agentlint.formats.claude_hooks import ClaudeHookFormatter

        formatter = ClaudeHookFormatter()
        assert formatter.format_subagent_start([]) is None


class TestWriteConfig:
    def test_preserves_non_hooks_dict_section(self, tmp_path) -> None:
        from agentlint.adapters.kimi import _write_config
        config_file = tmp_path / "config.toml"
        _write_config(config_file, {
            "hooks": [],
            "settings": {"theme": "dark"},
        })
        text = config_file.read_text()
        assert "[settings]" in text
        assert 'theme = "dark"' in text

    def test_preserves_non_hooks_str_int_float_bool(self, tmp_path) -> None:
        from agentlint.adapters.kimi import _write_config
        config_file = tmp_path / "config.toml"
        _write_config(config_file, {
            "hooks": [],
            "name": "test",
            "count": 42,
            "rate": 3.14,
            "enabled": True,
        })
        text = config_file.read_text()
        assert 'name = "test"' in text
        assert "count = 42" in text
        assert "rate = 3.14" in text
        assert "enabled = true" in text
