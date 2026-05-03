"""Tests for the Cursor IDE adapter."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agentlint.adapters.cursor import CursorAdapter, _build_hooks, _hooks_path
from agentlint.adapters._utils import is_agentlint_flat_entry
from agentlint.models import AgentEvent, HookEvent, NormalizedTool, RuleContext


class TestEventTranslation:
    def test_pre_tool_use(self) -> None:
        adapter = CursorAdapter()
        assert adapter.translate_event("preToolUse") == AgentEvent.PRE_TOOL_USE

    def test_post_tool_use(self) -> None:
        adapter = CursorAdapter()
        assert adapter.translate_event("postToolUse") == AgentEvent.POST_TOOL_USE

    def test_before_shell_execution(self) -> None:
        adapter = CursorAdapter()
        assert adapter.translate_event("beforeShellExecution") == AgentEvent.PRE_TOOL_USE

    def test_after_file_edit(self) -> None:
        adapter = CursorAdapter()
        assert adapter.translate_event("afterFileEdit") == AgentEvent.POST_TOOL_USE

    def test_stop(self) -> None:
        adapter = CursorAdapter()
        assert adapter.translate_event("stop") == AgentEvent.STOP

    def test_before_submit_prompt(self) -> None:
        adapter = CursorAdapter()
        assert adapter.translate_event("beforeSubmitPrompt") == AgentEvent.USER_PROMPT

    def test_unknown_event_raises(self) -> None:
        adapter = CursorAdapter()
        with pytest.raises(ValueError, match="Unknown Cursor event"):
            adapter.translate_event("unknownEvent")


class TestToolNormalization:
    def test_write(self) -> None:
        adapter = CursorAdapter()
        assert adapter.normalize_tool_name("Write") == NormalizedTool.FILE_WRITE.value

    def test_read(self) -> None:
        adapter = CursorAdapter()
        assert adapter.normalize_tool_name("Read") == NormalizedTool.FILE_READ.value

    def test_shell(self) -> None:
        adapter = CursorAdapter()
        assert adapter.normalize_tool_name("Shell") == NormalizedTool.SHELL.value

    def test_delete(self) -> None:
        adapter = CursorAdapter()
        assert adapter.normalize_tool_name("Delete") == NormalizedTool.FILE_WRITE.value

    def test_task(self) -> None:
        adapter = CursorAdapter()
        assert adapter.normalize_tool_name("Task") == NormalizedTool.SUB_AGENT.value

    def test_unknown(self) -> None:
        adapter = CursorAdapter()
        assert adapter.normalize_tool_name("UnknownTool") == NormalizedTool.UNKNOWN.value


class TestBuildRuleContext:
    def test_basic_context(self) -> None:
        adapter = CursorAdapter()
        context = adapter.build_rule_context(
            AgentEvent.PRE_TOOL_USE,
            {"tool_name": "Write", "tool_input": {"file_path": "test.py"}},
            "/project",
            {},
        )
        assert context.event == HookEvent.PRE_TOOL_USE
        assert context.tool_name == "Write"
        assert context.project_dir == "/project"
        assert context.agent_platform == "cursor"

    def test_subagent_fields(self) -> None:
        adapter = CursorAdapter()
        context = adapter.build_rule_context(
            AgentEvent.SUB_AGENT_STOP,
            {
                "tool_name": "Task",
                "tool_input": {},
                "subagent_type": "explore",
                "summary": "Done exploring",
            },
            "/project",
            {},
        )
        assert context.agent_type == "explore"
        assert context.subagent_output == "Done exploring"


class TestHooksPath:
    def test_project_scope(self, tmp_path) -> None:
        path = _hooks_path("project", str(tmp_path))
        assert path == tmp_path / ".cursor" / "hooks.json"

    def test_user_scope(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        path = _hooks_path("user")
        assert path == tmp_path / ".cursor" / "hooks.json"


class TestIsAgentlintEntry:
    def test_identifies_agentlint_entry(self) -> None:
        entry = {"command": "agentlint check --event preToolUse"}
        assert is_agentlint_flat_entry(entry) is True

    def test_identifies_absolute_path_entry(self) -> None:
        entry = {"command": "/usr/local/bin/agentlint check --event preToolUse"}
        assert is_agentlint_flat_entry(entry) is True

    def test_rejects_third_party_entry(self) -> None:
        entry = {"command": "my-other-tool check"}
        assert is_agentlint_flat_entry(entry) is False

    def test_handles_empty_command(self) -> None:
        assert is_agentlint_flat_entry({}) is False


class TestBuildHooks:
    EXPECTED_EVENTS = {
        "preToolUse", "postToolUse", "beforeShellExecution",
        "afterFileEdit", "beforeSubmitPrompt", "subagentStart",
        "subagentStop", "stop",
    }

    def test_builds_all_events(self) -> None:
        hooks = _build_hooks("agentlint")
        assert set(hooks["hooks"].keys()) == self.EXPECTED_EVENTS

    def test_embeds_bare_command(self) -> None:
        hooks = _build_hooks("agentlint")
        pre_cmd = hooks["hooks"]["preToolUse"][0]["command"]
        assert pre_cmd == "agentlint check --event preToolUse --adapter cursor"

    def test_timeouts_are_correct(self) -> None:
        hooks = _build_hooks("agentlint")
        assert hooks["hooks"]["preToolUse"][0]["timeout"] == 5
        assert hooks["hooks"]["postToolUse"][0]["timeout"] == 10
        assert hooks["hooks"]["stop"][0]["timeout"] == 30


class TestInstallHooks:
    def test_creates_hooks_json(self, tmp_path) -> None:
        adapter = CursorAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        hooks_file = tmp_path / ".cursor" / "hooks.json"
        assert hooks_file.exists()
        data = json.loads(hooks_file.read_text())
        assert data["version"] == 1
        assert "hooks" in data
        assert set(data["hooks"].keys()) == TestBuildHooks.EXPECTED_EVENTS

    def test_idempotent_install(self, tmp_path) -> None:
        adapter = CursorAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        first = (tmp_path / ".cursor" / "hooks.json").read_text()

        adapter.install_hooks(str(tmp_path), scope="project")
        second = (tmp_path / ".cursor" / "hooks.json").read_text()

        assert first == second

    def test_preserves_existing_hooks(self, tmp_path) -> None:
        hooks_file = tmp_path / ".cursor" / "hooks.json"
        hooks_file.parent.mkdir(parents=True)
        existing = {
            "version": 1,
            "hooks": {
                "afterFileEdit": [
                    {"command": "biome format {file.path}"}
                ]
            }
        }
        hooks_file.write_text(json.dumps(existing))

        adapter = CursorAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")

        data = json.loads(hooks_file.read_text())
        after_edit = data["hooks"]["afterFileEdit"]
        assert len(after_edit) == 2
        assert after_edit[0]["command"] == "biome format {file.path}"
        assert "agentlint" in after_edit[1]["command"]

    def test_dry_run_does_not_write(self, tmp_path) -> None:
        adapter = CursorAdapter()
        adapter.install_hooks(str(tmp_path), scope="project", dry_run=True)

        hooks_file = tmp_path / ".cursor" / "hooks.json"
        assert not hooks_file.exists()


class TestUninstallHooks:
    def test_removes_hooks(self, tmp_path) -> None:
        adapter = CursorAdapter()
        adapter.install_hooks(str(tmp_path), scope="project")
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        hooks_file = tmp_path / ".cursor" / "hooks.json"
        assert not hooks_file.exists()

    def test_preserves_other_hooks(self, tmp_path) -> None:
        hooks_file = tmp_path / ".cursor" / "hooks.json"
        hooks_file.parent.mkdir(parents=True)
        existing = {
            "version": 1,
            "hooks": {
                "afterFileEdit": [
                    {"command": "biome format {file.path}"},
                    {"command": "agentlint check --event afterFileEdit --adapter cursor"},
                ]
            }
        }
        hooks_file.write_text(json.dumps(existing))

        adapter = CursorAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        data = json.loads(hooks_file.read_text())
        assert len(data["hooks"]["afterFileEdit"]) == 1
        assert data["hooks"]["afterFileEdit"][0]["command"] == "biome format {file.path}"

    def test_noop_when_not_installed(self, tmp_path) -> None:
        adapter = CursorAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")
        assert not (tmp_path / ".cursor" / "hooks.json").exists()


class TestFormatter:
    def test_exit_code_blocked(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.cursor_hooks import CursorHookFormatter

        formatter = CursorHookFormatter()
        violations = [Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR)]
        assert formatter.exit_code(violations, AgentEvent.PRE_TOOL_USE) == 2

    def test_exit_code_allowed(self) -> None:
        from agentlint.formats.cursor_hooks import CursorHookFormatter

        formatter = CursorHookFormatter()
        assert formatter.exit_code([], AgentEvent.PRE_TOOL_USE) == 0

    def test_blocking_format(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.cursor_hooks import CursorHookFormatter

        formatter = CursorHookFormatter()
        violations = [Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR)]
        output = formatter.format(violations, AgentEvent.PRE_TOOL_USE)
        assert output is not None
        data = json.loads(output)
        assert data["permission"] == "deny"
        assert "agent_message" in data

    def test_advisory_format(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.cursor_hooks import CursorHookFormatter

        formatter = CursorHookFormatter()
        violations = [Violation(rule_id="max-file-size", message="File too large", severity=Severity.WARNING)]
        output = formatter.format(violations, AgentEvent.POST_TOOL_USE)
        assert output is not None
        data = json.loads(output)
        assert "additional_context" in data

    def test_format_returns_none_when_no_violations(self) -> None:
        from agentlint.formats.cursor_hooks import CursorHookFormatter

        formatter = CursorHookFormatter()
        assert formatter.format([], AgentEvent.PRE_TOOL_USE) is None

    def test_format_fallback_for_stop_event(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.cursor_hooks import CursorHookFormatter

        formatter = CursorHookFormatter()
        violations = [Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR)]
        output = formatter.format(violations, AgentEvent.STOP)
        assert output is not None
        data = json.loads(output)
        assert "additional_context" in data

    def test_format_subagent_start(self) -> None:
        from agentlint.models import Severity, Violation
        from agentlint.formats.cursor_hooks import CursorHookFormatter

        formatter = CursorHookFormatter()
        violations = [Violation(rule_id="no-secrets", message="Secret found", severity=Severity.ERROR)]
        output = formatter.format_subagent_start(violations)
        assert output is not None
        data = json.loads(output)
        assert "additional_context" in data

    def test_format_subagent_start_returns_none(self) -> None:
        from agentlint.formats.cursor_hooks import CursorHookFormatter

        formatter = CursorHookFormatter()
        assert formatter.format_subagent_start([]) is None


class TestEnvFallbacks:
    def test_resolves_project_dir_from_agentlint_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENTLINT_PROJECT_DIR", "/my/agentlint/project")
        adapter = CursorAdapter()
        assert adapter.resolve_project_dir() == "/my/agentlint/project"

    def test_resolves_session_key_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENTLINT_SESSION_ID", "session-123")
        adapter = CursorAdapter()
        assert adapter.resolve_session_key() == "session-123"


class TestUninstallHooks:
    def test_uninstall_flat_entry(self, tmp_path) -> None:
        hooks_file = tmp_path / ".cursor" / "hooks.json"
        hooks_file.parent.mkdir(parents=True)
        existing = {
            "version": 1,
            "hooks": {
                "stop": {"_agentlint": "v2", "command": "agentlint check --event stop --adapter cursor"},
                "preToolUse": [{"command": "echo hello"}],
            }
        }
        hooks_file.write_text(json.dumps(existing))
        adapter = CursorAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")
        data = json.loads(hooks_file.read_text())
        assert "stop" not in data["hooks"]
        assert "preToolUse" in data["hooks"]
