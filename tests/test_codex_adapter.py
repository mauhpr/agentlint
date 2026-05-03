"""Tests for the Codex CLI adapter."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentlint.adapters.codex import CodexAdapter, _build_hooks, _hooks_path
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext


class TestEventTranslation:
    def test_pre_tool_use(self) -> None:
        adapter = CodexAdapter()
        assert adapter.translate_event("PreToolUse") == AgentEvent.PRE_TOOL_USE

    def test_post_tool_use(self) -> None:
        adapter = CodexAdapter()
        assert adapter.translate_event("PostToolUse") == AgentEvent.POST_TOOL_USE

    def test_stop(self) -> None:
        adapter = CodexAdapter()
        assert adapter.translate_event("Stop") == AgentEvent.STOP

    def test_after_agent(self) -> None:
        adapter = CodexAdapter()
        assert adapter.translate_event("AfterAgent") == AgentEvent.STOP

    def test_after_tool_use(self) -> None:
        adapter = CodexAdapter()
        assert adapter.translate_event("AfterToolUse") == AgentEvent.POST_TOOL_USE

    def test_unknown_event_raises(self) -> None:
        adapter = CodexAdapter()
        with pytest.raises(ValueError, match="Unknown Codex event"):
            adapter.translate_event("unknownEvent")


class TestToolNormalization:
    def test_bash(self) -> None:
        adapter = CodexAdapter()
        assert adapter.normalize_tool_name("Bash") == NormalizedTool.SHELL.value

    def test_apply_patch(self) -> None:
        adapter = CodexAdapter()
        assert adapter.normalize_tool_name("apply_patch") == NormalizedTool.FILE_EDIT.value

    def test_read(self) -> None:
        adapter = CodexAdapter()
        assert adapter.normalize_tool_name("Read") == NormalizedTool.FILE_READ.value

    def test_unknown(self) -> None:
        adapter = CodexAdapter()
        assert adapter.normalize_tool_name("UnknownTool") == NormalizedTool.UNKNOWN.value


class TestBuildRuleContext:
    def test_basic_context(self) -> None:
        adapter = CodexAdapter()
        context = adapter.build_rule_context(
            AgentEvent.PRE_TOOL_USE,
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            "/project",
            {},
        )
        assert context.event == HookEvent.PRE_TOOL_USE
        assert context.tool_name == "Bash"
        assert context.agent_platform == "codex"

    def test_resolves_project_dir_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("CODEX_PROJECT_DIR", "/my/codex/project")
        adapter = CodexAdapter()
        assert adapter.resolve_project_dir() == "/my/codex/project"


class TestHooksPath:
    def test_project_scope(self, tmp_path) -> None:
        path = _hooks_path("project", str(tmp_path))
        assert path == tmp_path / ".codex" / "hooks.json"

    def test_user_scope(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        path = _hooks_path("user")
        assert path == tmp_path / ".codex" / "hooks.json"


class TestBuildHooks:
    EXPECTED_EVENTS = {
        "PreToolUse", "PostToolUse", "UserPromptSubmit",
        "SessionStart", "Stop",
    }

    def test_builds_all_events(self) -> None:
        hooks = _build_hooks("agentlint")
        assert set(hooks["hooks"].keys()) == self.EXPECTED_EVENTS

    def test_bash_matcher(self) -> None:
        hooks = _build_hooks("agentlint")
        assert hooks["hooks"]["PreToolUse"][0]["matcher"] == "^Bash$"

    def test_embeds_adapter_flag(self) -> None:
        hooks = _build_hooks("agentlint")
        pre_cmd = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert "--adapter codex" in pre_cmd


class TestInstallHooks:
    def test_creates_hooks_json(self, tmp_path) -> None:
        adapter = CodexAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        hooks_file = tmp_path / ".codex" / "hooks.json"
        assert hooks_file.exists()
        data = json.loads(hooks_file.read_text())
        assert "hooks" in data
        assert set(data["hooks"].keys()) == TestBuildHooks.EXPECTED_EVENTS

    def test_idempotent_install(self, tmp_path) -> None:
        adapter = CodexAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        first = (tmp_path / ".codex" / "hooks.json").read_text()

        adapter.install_hooks(str(tmp_path), scope="project")
        second = (tmp_path / ".codex" / "hooks.json").read_text()

        assert first == second

    def test_preserves_existing_hooks(self, tmp_path) -> None:
        hooks_file = tmp_path / ".codex" / "hooks.json"
        hooks_file.parent.mkdir(parents=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "^Bash$", "hooks": [{"type": "command", "command": "echo hello"}]}
                ]
            }
        }
        hooks_file.write_text(json.dumps(existing))

        adapter = CodexAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        data = json.loads(hooks_file.read_text())
        pre_tool = data["hooks"]["PreToolUse"]
        assert len(pre_tool) == 2
        assert pre_tool[0]["hooks"][0]["command"] == "echo hello"
        assert "agentlint" in pre_tool[1]["hooks"][0]["command"]


class TestUninstallHooks:
    def test_removes_hooks(self, tmp_path) -> None:
        adapter = CodexAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        hooks_file = tmp_path / ".codex" / "hooks.json"
        assert not hooks_file.exists()

    def test_preserves_other_hooks(self, tmp_path) -> None:
        hooks_file = tmp_path / ".codex" / "hooks.json"
        hooks_file.parent.mkdir(parents=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "^Bash$", "hooks": [{"type": "command", "command": "echo hello"}]},
                    {"matcher": "^Bash$", "hooks": [{"type": "command", "command": "agentlint check --event PreToolUse --adapter codex"}]},
                ]
            }
        }
        hooks_file.write_text(json.dumps(existing))

        adapter = CodexAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["PreToolUse"]) == 1
        assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo hello"


class TestFormatter:
    def test_uses_claude_formatter(self) -> None:
        from agentlint.formats.claude_hooks import ClaudeHookFormatter
        adapter = CodexAdapter()
        assert isinstance(adapter.formatter, ClaudeHookFormatter)
