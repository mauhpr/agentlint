"""Tests for the Continue.dev CLI adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlint.adapters.continue_dev import ContinueAdapter, _build_hooks, _settings_path
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext


class TestEventTranslation:
    def test_pre_tool_use(self) -> None:
        adapter = ContinueAdapter()
        assert adapter.translate_event("PreToolUse") == AgentEvent.PRE_TOOL_USE

    def test_post_tool_use(self) -> None:
        adapter = ContinueAdapter()
        assert adapter.translate_event("PostToolUse") == AgentEvent.POST_TOOL_USE

    def test_stop(self) -> None:
        adapter = ContinueAdapter()
        assert adapter.translate_event("Stop") == AgentEvent.STOP

    def test_permission_request(self) -> None:
        adapter = ContinueAdapter()
        assert adapter.translate_event("PermissionRequest") == AgentEvent.PERMISSION_REQUEST

    def test_worktree_create(self) -> None:
        adapter = ContinueAdapter()
        assert adapter.translate_event("WorktreeCreate") == AgentEvent.WORKTREE_CREATE

    def test_unknown_event_raises(self) -> None:
        adapter = ContinueAdapter()
        with pytest.raises(ValueError, match="Unknown Continue event"):
            adapter.translate_event("unknownEvent")


class TestToolNormalization:
    def test_bash(self) -> None:
        adapter = ContinueAdapter()
        assert adapter.normalize_tool_name("Bash") == NormalizedTool.SHELL.value

    def test_write(self) -> None:
        adapter = ContinueAdapter()
        assert adapter.normalize_tool_name("Write") == NormalizedTool.FILE_WRITE.value

    def test_edit(self) -> None:
        adapter = ContinueAdapter()
        assert adapter.normalize_tool_name("Edit") == NormalizedTool.FILE_EDIT.value

    def test_task(self) -> None:
        adapter = ContinueAdapter()
        assert adapter.normalize_tool_name("Task") == NormalizedTool.SUB_AGENT.value

    def test_unknown(self) -> None:
        adapter = ContinueAdapter()
        assert adapter.normalize_tool_name("UnknownTool") == NormalizedTool.UNKNOWN.value


class TestBuildRuleContext:
    def test_basic_context(self) -> None:
        adapter = ContinueAdapter()
        context = adapter.build_rule_context(
            AgentEvent.PRE_TOOL_USE,
            {"tool_name": "Write", "tool_input": {"file_path": "test.py"}},
            "/project",
            {},
        )
        assert context.event == HookEvent.PRE_TOOL_USE
        assert context.tool_name == "Write"
        assert context.agent_platform == "continue"

    def test_resolves_project_dir_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("CONTINUE_PROJECT_DIR", "/my/continue/project")
        adapter = ContinueAdapter()
        assert adapter.resolve_project_dir() == "/my/continue/project"


class TestSettingsPath:
    def test_project_scope(self, tmp_path) -> None:
        path = _settings_path("project", str(tmp_path))
        assert path == tmp_path / ".continue" / "settings.json"

    def test_user_scope(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        path = _settings_path("user")
        assert path == tmp_path / ".continue" / "settings.json"


class TestBuildHooks:
    EXPECTED_EVENTS = {
        "PreToolUse", "PostToolUse", "UserPromptSubmit",
        "SubagentStart", "SubagentStop", "Notification", "Stop",
    }

    def test_builds_all_events(self) -> None:
        hooks = _build_hooks("agentlint")
        assert set(hooks.keys()) == self.EXPECTED_EVENTS

    def test_embeds_adapter_flag(self) -> None:
        hooks = _build_hooks("agentlint")
        pre_cmd = hooks["PreToolUse"][0]["hooks"][0]["command"]
        assert "--adapter continue" in pre_cmd


class TestInstallHooks:
    def test_creates_settings_json(self, tmp_path) -> None:
        adapter = ContinueAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        settings_file = tmp_path / ".continue" / "settings.json"
        assert settings_file.exists()
        data = json.loads(settings_file.read_text())
        assert "hooks" in data
        assert set(data["hooks"].keys()) == TestBuildHooks.EXPECTED_EVENTS

    def test_idempotent_install(self, tmp_path) -> None:
        adapter = ContinueAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        first = (tmp_path / ".continue" / "settings.json").read_text()

        adapter.install_hooks(str(tmp_path), scope="project")
        second = (tmp_path / ".continue" / "settings.json").read_text()

        assert first == second

    def test_preserves_existing_hooks(self, tmp_path) -> None:
        settings_file = tmp_path / ".continue" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash|Edit|Write", "hooks": [{"type": "command", "command": "echo hello"}]}
                ]
            }
        }
        settings_file.write_text(json.dumps(existing))

        adapter = ContinueAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        data = json.loads(settings_file.read_text())
        pre_tool = data["hooks"]["PreToolUse"]
        assert len(pre_tool) == 2
        assert pre_tool[0]["hooks"][0]["command"] == "echo hello"
        assert "agentlint" in pre_tool[1]["hooks"][0]["command"]


class TestUninstallHooks:
    def test_removes_hooks(self, tmp_path) -> None:
        adapter = ContinueAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        settings_file = tmp_path / ".continue" / "settings.json"
        assert not settings_file.exists()

    def test_preserves_other_hooks(self, tmp_path) -> None:
        settings_file = tmp_path / ".continue" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash|Edit|Write", "hooks": [{"type": "command", "command": "echo hello"}]},
                    {"matcher": "Bash|Edit|Write", "hooks": [{"type": "command", "command": "agentlint check --event PreToolUse --adapter continue"}]},
                ]
            }
        }
        settings_file.write_text(json.dumps(existing))

        adapter = ContinueAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        data = json.loads(settings_file.read_text())
        assert len(data["hooks"]["PreToolUse"]) == 1
        assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo hello"


class TestFormatter:
    def test_uses_claude_formatter(self) -> None:
        from agentlint.formats.claude_hooks import ClaudeHookFormatter
        adapter = ContinueAdapter()
        assert isinstance(adapter.formatter, ClaudeHookFormatter)
