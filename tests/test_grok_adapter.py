"""Tests for the Grok CLI adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlint.adapters.grok import GrokAdapter, _build_hooks, _settings_path as _hooks_path
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext


class TestEventTranslation:
    def test_pre_tool_use(self) -> None:
        adapter = GrokAdapter()
        assert adapter.translate_event("PreToolUse") == AgentEvent.PRE_TOOL_USE

    def test_post_tool_use(self) -> None:
        adapter = GrokAdapter()
        assert adapter.translate_event("PostToolUse") == AgentEvent.POST_TOOL_USE

    def test_stop(self) -> None:
        adapter = GrokAdapter()
        assert adapter.translate_event("Stop") == AgentEvent.STOP

    def test_task_created(self) -> None:
        adapter = GrokAdapter()
        assert adapter.translate_event("TaskCreated") == AgentEvent.SUB_AGENT_START

    def test_task_completed(self) -> None:
        adapter = GrokAdapter()
        assert adapter.translate_event("TaskCompleted") == AgentEvent.TASK_COMPLETED

    def test_unknown_event_raises(self) -> None:
        adapter = GrokAdapter()
        with pytest.raises(ValueError, match="Unknown Grok event"):
            adapter.translate_event("unknownEvent")


class TestToolNormalization:
    def test_bash(self) -> None:
        adapter = GrokAdapter()
        assert adapter.normalize_tool_name("bash") == NormalizedTool.SHELL.value

    def test_write(self) -> None:
        adapter = GrokAdapter()
        assert adapter.normalize_tool_name("write") == NormalizedTool.FILE_WRITE.value

    def test_edit(self) -> None:
        adapter = GrokAdapter()
        assert adapter.normalize_tool_name("edit") == NormalizedTool.FILE_EDIT.value

    def test_delegate(self) -> None:
        adapter = GrokAdapter()
        assert adapter.normalize_tool_name("delegate") == NormalizedTool.SUB_AGENT.value

    def test_search_web(self) -> None:
        adapter = GrokAdapter()
        assert adapter.normalize_tool_name("search_web") == NormalizedTool.WEB_SEARCH.value

    def test_unknown(self) -> None:
        adapter = GrokAdapter()
        assert adapter.normalize_tool_name("unknown") == NormalizedTool.UNKNOWN.value


class TestBuildRuleContext:
    def test_basic_context(self) -> None:
        adapter = GrokAdapter()
        context = adapter.build_rule_context(
            AgentEvent.PRE_TOOL_USE,
            {"tool_name": "bash", "tool_input": {"command": "ls"}},
            "/project",
            {},
        )
        assert context.event == HookEvent.PRE_TOOL_USE
        assert context.tool_name == "bash"
        assert context.agent_platform == "grok"

    def test_resolves_project_dir_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("GROK_PROJECT_DIR", "/my/grok/project")
        adapter = GrokAdapter()
        assert adapter.resolve_project_dir() == "/my/grok/project"


class TestHooksPath:
    def test_project_scope(self, tmp_path) -> None:
        path = _hooks_path("project", str(tmp_path))
        assert path == tmp_path / ".grok" / "settings.json"

    def test_user_scope(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        path = _hooks_path("user")
        assert path == tmp_path / ".grok" / "user-settings.json"


class TestBuildHooks:
    EXPECTED_EVENTS = {
        "PreToolUse", "PostToolUse", "UserPromptSubmit",
        "SubagentStart", "SubagentStop", "Notification", "Stop",
    }

    def test_builds_all_events(self) -> None:
        hooks = _build_hooks("agentlint")
        assert set(hooks["hooks"].keys()) == self.EXPECTED_EVENTS

    def test_embeds_adapter_flag(self) -> None:
        hooks = _build_hooks("agentlint")
        pre_cmd = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert "--adapter grok" in pre_cmd


class TestInstallHooks:
    def test_creates_settings_json(self, tmp_path) -> None:
        adapter = GrokAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        settings_file = tmp_path / ".grok" / "settings.json"
        assert settings_file.exists()
        data = json.loads(settings_file.read_text())
        assert "hooks" in data
        assert set(data["hooks"].keys()) == TestBuildHooks.EXPECTED_EVENTS

    def test_idempotent_install(self, tmp_path) -> None:
        adapter = GrokAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        first = (tmp_path / ".grok" / "settings.json").read_text()

        adapter.install_hooks(str(tmp_path), scope="project")
        second = (tmp_path / ".grok" / "settings.json").read_text()

        assert first == second

    def test_preserves_existing_hooks(self, tmp_path) -> None:
        settings_file = tmp_path / ".grok" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "bash", "hooks": [{"type": "command", "command": "echo hello"}]}
                ]
            }
        }
        settings_file.write_text(json.dumps(existing))

        adapter = GrokAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        data = json.loads(settings_file.read_text())
        pre_tool = data["hooks"]["PreToolUse"]
        assert len(pre_tool) == 2
        assert pre_tool[0]["hooks"][0]["command"] == "echo hello"
        assert "agentlint" in pre_tool[1]["hooks"][0]["command"]


class TestUninstallHooks:
    def test_removes_hooks(self, tmp_path) -> None:
        adapter = GrokAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        settings_file = tmp_path / ".grok" / "settings.json"
        assert not settings_file.exists()

    def test_preserves_other_hooks(self, tmp_path) -> None:
        settings_file = tmp_path / ".grok" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "bash", "hooks": [{"type": "command", "command": "echo hello"}]},
                    {"matcher": "bash", "hooks": [{"type": "command", "command": "agentlint check --event PreToolUse --adapter grok"}]},
                ]
            }
        }
        settings_file.write_text(json.dumps(existing))

        adapter = GrokAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        data = json.loads(settings_file.read_text())
        assert len(data["hooks"]["PreToolUse"]) == 1
        assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo hello"


class TestFormatter:
    def test_uses_claude_formatter(self) -> None:
        from agentlint.formats.claude_hooks import ClaudeHookFormatter
        adapter = GrokAdapter()
        assert isinstance(adapter.formatter, ClaudeHookFormatter)


class TestEnvFallbacks:
    def test_resolves_session_key_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENTLINT_SESSION_ID", "session-123")
        adapter = GrokAdapter()
        assert adapter.resolve_session_key() == "session-123"


class TestInstallHooksExtra:
    def test_dry_run_does_not_write(self, tmp_path) -> None:
        adapter = GrokAdapter()
        adapter.install_hooks(str(tmp_path), scope="project", dry_run=True)
        assert not (tmp_path / ".grok" / "settings.json").exists()


class TestUninstallHooksExtra:
    def test_uninstall_aborts_on_corrupted_file(self, tmp_path) -> None:
        settings_file = tmp_path / ".grok" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text("not json")
        adapter = GrokAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")
        assert settings_file.read_text() == "not json"
