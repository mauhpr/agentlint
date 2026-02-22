"""Tests for agentlint setup/uninstall (hook installation)."""
from __future__ import annotations

import json
import sys
from unittest.mock import patch

from click.testing import CliRunner

from agentlint.cli import main
from agentlint.setup import (
    AGENTLINT_HOOKS,
    _is_agentlint_entry,
    _resolve_command,
    build_hooks,
    merge_hooks,
    read_settings,
    remove_hooks,
    settings_path,
    write_settings,
)


class TestSettingsPath:
    def test_project_scope(self, tmp_path) -> None:
        path = settings_path("project", str(tmp_path))
        assert path == tmp_path / ".claude" / "settings.json"

    def test_user_scope(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("HOME", str(tmp_path))
        path = settings_path("user")
        assert path == tmp_path / ".claude" / "settings.json"

    def test_project_scope_default_cwd(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        path = settings_path("project")
        assert path == tmp_path / ".claude" / "settings.json"


class TestReadSettings:
    def test_reads_valid_json(self, tmp_path) -> None:
        f = tmp_path / "settings.json"
        f.write_text('{"hooks": {}}')
        assert read_settings(f) == {"hooks": {}}

    def test_returns_empty_dict_for_missing_file(self, tmp_path) -> None:
        f = tmp_path / "nonexistent.json"
        assert read_settings(f) == {}

    def test_returns_empty_dict_for_invalid_json(self, tmp_path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{not valid json")
        assert read_settings(f) == {}


class TestWriteSettings:
    def test_writes_json_with_indent(self, tmp_path) -> None:
        f = tmp_path / "out.json"
        write_settings(f, {"key": "value"})
        content = f.read_text()
        assert '"key": "value"' in content
        assert content.startswith("{\n")
        assert content.endswith("}\n")

    def test_creates_parent_dirs(self, tmp_path) -> None:
        f = tmp_path / ".claude" / "settings.json"
        write_settings(f, {"a": 1})
        assert f.exists()
        assert json.loads(f.read_text()) == {"a": 1}


class TestIsAgentlintEntry:
    def test_identifies_agentlint_entry(self) -> None:
        entry = {"hooks": [{"type": "command", "command": "agentlint check --event PreToolUse"}]}
        assert _is_agentlint_entry(entry) is True

    def test_identifies_absolute_path_entry(self) -> None:
        entry = {"hooks": [{"type": "command", "command": "/usr/local/bin/agentlint check --event PreToolUse"}]}
        assert _is_agentlint_entry(entry) is True

    def test_identifies_python_m_entry(self) -> None:
        entry = {"hooks": [{"type": "command", "command": "/usr/bin/python -m agentlint check --event PreToolUse"}]}
        assert _is_agentlint_entry(entry) is True

    def test_rejects_third_party_entry(self) -> None:
        entry = {"hooks": [{"type": "command", "command": "my-other-tool check"}]}
        assert _is_agentlint_entry(entry) is False

    def test_handles_empty_hooks(self) -> None:
        assert _is_agentlint_entry({}) is False
        assert _is_agentlint_entry({"hooks": []}) is False


class TestResolveCommand:
    def test_returns_absolute_path_when_which_succeeds(self) -> None:
        with patch("agentlint.setup.shutil.which", return_value="/usr/local/bin/agentlint"):
            result = _resolve_command()
        assert result == "/usr/local/bin/agentlint"

    def test_falls_back_to_sys_executable_when_which_fails(self) -> None:
        with patch("agentlint.setup.shutil.which", return_value=None):
            result = _resolve_command()
        assert result == f"{sys.executable} -m agentlint"

    def test_which_none_uses_current_python(self) -> None:
        with patch("agentlint.setup.shutil.which", return_value=None), \
             patch("agentlint.setup.sys") as mock_sys:
            mock_sys.executable = "/opt/venv/bin/python"
            result = _resolve_command()
        assert result == "/opt/venv/bin/python -m agentlint"

    def test_returns_string(self) -> None:
        result = _resolve_command()
        assert isinstance(result, str)
        assert "agentlint" in result


class TestBuildHooks:
    EXPECTED_EVENTS = {"PreToolUse", "PostToolUse", "UserPromptSubmit", "SubagentStop", "Notification", "Stop"}

    def test_builds_all_events(self) -> None:
        hooks = build_hooks("agentlint")
        assert set(hooks.keys()) == self.EXPECTED_EVENTS

    def test_embeds_bare_command(self) -> None:
        hooks = build_hooks("agentlint")
        pre_cmd = hooks["PreToolUse"][0]["hooks"][0]["command"]
        post_cmd = hooks["PostToolUse"][0]["hooks"][0]["command"]
        stop_cmd = hooks["Stop"][0]["hooks"][0]["command"]
        prompt_cmd = hooks["UserPromptSubmit"][0]["hooks"][0]["command"]
        assert pre_cmd == "agentlint check --event PreToolUse"
        assert post_cmd == "agentlint check --event PostToolUse"
        assert stop_cmd == "agentlint report"
        assert prompt_cmd == "agentlint check --event UserPromptSubmit"

    def test_embeds_absolute_path(self) -> None:
        hooks = build_hooks("/usr/local/bin/agentlint")
        pre_cmd = hooks["PreToolUse"][0]["hooks"][0]["command"]
        post_cmd = hooks["PostToolUse"][0]["hooks"][0]["command"]
        stop_cmd = hooks["Stop"][0]["hooks"][0]["command"]
        assert pre_cmd == "/usr/local/bin/agentlint check --event PreToolUse"
        assert post_cmd == "/usr/local/bin/agentlint check --event PostToolUse"
        assert stop_cmd == "/usr/local/bin/agentlint report"

    def test_embeds_python_m_command(self) -> None:
        hooks = build_hooks("/opt/venv/bin/python -m agentlint")
        pre_cmd = hooks["PreToolUse"][0]["hooks"][0]["command"]
        assert pre_cmd == "/opt/venv/bin/python -m agentlint check --event PreToolUse"

    def test_matches_agentlint_hooks_constant(self) -> None:
        """AGENTLINT_HOOKS backward-compat alias equals build_hooks('agentlint')."""
        assert build_hooks("agentlint") == AGENTLINT_HOOKS

    def test_timeouts_are_correct(self) -> None:
        hooks = build_hooks("agentlint")
        assert hooks["PreToolUse"][0]["hooks"][0]["timeout"] == 5
        assert hooks["PostToolUse"][0]["hooks"][0]["timeout"] == 10
        assert hooks["UserPromptSubmit"][0]["hooks"][0]["timeout"] == 5
        assert hooks["SubagentStop"][0]["hooks"][0]["timeout"] == 10
        assert hooks["Notification"][0]["hooks"][0]["timeout"] == 5
        assert hooks["Stop"][0]["hooks"][0]["timeout"] == 30

    def test_new_events_use_check_command(self) -> None:
        hooks = build_hooks("agentlint")
        for event in ("UserPromptSubmit", "SubagentStop", "Notification"):
            cmd = hooks[event][0]["hooks"][0]["command"]
            assert cmd == f"agentlint check --event {event}"


class TestMergeHooks:
    def test_merges_into_empty_settings(self) -> None:
        result = merge_hooks({}, agentlint_cmd="agentlint")
        assert "hooks" in result
        assert set(result["hooks"].keys()) == TestBuildHooks.EXPECTED_EVENTS

    def test_preserves_third_party_hooks(self) -> None:
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "other-tool lint"}]}
                ]
            }
        }
        result = merge_hooks(existing, agentlint_cmd="agentlint")
        pre_hooks = result["hooks"]["PreToolUse"]
        # Should have the third-party entry + our entry
        assert len(pre_hooks) == 2
        assert pre_hooks[0]["hooks"][0]["command"] == "other-tool lint"
        assert _is_agentlint_entry(pre_hooks[1])

    def test_idempotent_merge(self) -> None:
        first = merge_hooks({}, agentlint_cmd="agentlint")
        second = merge_hooks(first, agentlint_cmd="agentlint")
        assert first == second

    def test_replaces_existing_agentlint_entries(self) -> None:
        # Simulate an old installation with a different timeout
        existing = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash|Edit|Write",
                        "hooks": [{"type": "command", "command": "agentlint check --event PreToolUse", "timeout": 99}],
                    }
                ]
            }
        }
        result = merge_hooks(existing, agentlint_cmd="agentlint")
        pre_hooks = result["hooks"]["PreToolUse"]
        assert len(pre_hooks) == 1
        assert pre_hooks[0]["hooks"][0]["timeout"] == 5  # Updated to current

    def test_preserves_non_hook_settings(self) -> None:
        existing = {"other_key": "value", "hooks": {}}
        result = merge_hooks(existing, agentlint_cmd="agentlint")
        assert result["other_key"] == "value"

    def test_embeds_absolute_path_in_hooks(self) -> None:
        result = merge_hooks({}, agentlint_cmd="/usr/local/bin/agentlint")
        pre_cmd = result["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        post_cmd = result["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        stop_cmd = result["hooks"]["Stop"][0]["hooks"][0]["command"]
        assert pre_cmd == "/usr/local/bin/agentlint check --event PreToolUse"
        assert post_cmd == "/usr/local/bin/agentlint check --event PostToolUse"
        assert stop_cmd == "/usr/local/bin/agentlint report"

    def test_replaces_bare_with_absolute_path(self) -> None:
        """Re-running setup upgrades bare 'agentlint' to an absolute path."""
        old = merge_hooks({}, agentlint_cmd="agentlint")
        updated = merge_hooks(old, agentlint_cmd="/usr/local/bin/agentlint")
        pre_cmd = updated["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert pre_cmd == "/usr/local/bin/agentlint check --event PreToolUse"
        # Only one entry (old one replaced)
        assert len(updated["hooks"]["PreToolUse"]) == 1

    def test_uses_resolve_command_when_no_cmd_given(self) -> None:
        with patch("agentlint.setup._resolve_command", return_value="/mock/bin/agentlint"):
            result = merge_hooks({})
        pre_cmd = result["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert pre_cmd == "/mock/bin/agentlint check --event PreToolUse"


class TestRemoveHooks:
    def test_removes_agentlint_entries(self) -> None:
        installed = merge_hooks({}, agentlint_cmd="agentlint")
        result = remove_hooks(installed)
        assert "hooks" not in result

    def test_removes_absolute_path_entries(self) -> None:
        installed = merge_hooks({}, agentlint_cmd="/usr/local/bin/agentlint")
        result = remove_hooks(installed)
        assert "hooks" not in result

    def test_removes_python_m_entries(self) -> None:
        installed = merge_hooks({}, agentlint_cmd="/opt/venv/bin/python -m agentlint")
        result = remove_hooks(installed)
        assert "hooks" not in result

    def test_preserves_third_party_hooks(self) -> None:
        existing = merge_hooks({
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"type": "command", "command": "other-tool lint"}]}
                ]
            }
        }, agentlint_cmd="agentlint")
        result = remove_hooks(existing)
        assert "PreToolUse" in result["hooks"]
        assert len(result["hooks"]["PreToolUse"]) == 1
        assert result["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "other-tool lint"

    def test_removes_empty_event_keys(self) -> None:
        installed = merge_hooks({}, agentlint_cmd="agentlint")
        result = remove_hooks(installed)
        assert "hooks" not in result

    def test_noop_on_empty_settings(self) -> None:
        result = remove_hooks({})
        assert result == {}

    def test_preserves_non_hook_settings(self) -> None:
        installed = merge_hooks({"other_key": "value"}, agentlint_cmd="agentlint")
        result = remove_hooks(installed)
        assert result == {"other_key": "value"}


class TestSetupCLI:
    def test_setup_creates_settings_file(self, tmp_path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["setup", "--project-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "Installed" in result.output
        assert "Resolved agentlint:" in result.output

        settings_file = tmp_path / ".claude" / "settings.json"
        assert settings_file.exists()
        data = json.loads(settings_file.read_text())
        assert "hooks" in data
        assert set(data["hooks"].keys()) == TestBuildHooks.EXPECTED_EVENTS

    def test_setup_embeds_resolved_path(self, tmp_path) -> None:
        runner = CliRunner()
        with patch("agentlint.cli._resolve_command", return_value="/mock/bin/agentlint"):
            result = runner.invoke(main, ["setup", "--project-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "/mock/bin/agentlint" in result.output

        settings_file = tmp_path / ".claude" / "settings.json"
        data = json.loads(settings_file.read_text())
        pre_cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        assert pre_cmd == "/mock/bin/agentlint check --event PreToolUse"

    def test_setup_also_creates_config(self, tmp_path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["setup", "--project-dir", str(tmp_path)])

        assert result.exit_code == 0
        config_path = tmp_path / "agentlint.yml"
        assert config_path.exists()

    def test_setup_does_not_overwrite_existing_config(self, tmp_path) -> None:
        config_path = tmp_path / "agentlint.yml"
        config_path.write_text("custom: config\n")

        runner = CliRunner()
        runner.invoke(main, ["setup", "--project-dir", str(tmp_path)])

        assert config_path.read_text() == "custom: config\n"

    def test_setup_idempotent(self, tmp_path) -> None:
        runner = CliRunner()
        runner.invoke(main, ["setup", "--project-dir", str(tmp_path)])
        first = (tmp_path / ".claude" / "settings.json").read_text()

        runner.invoke(main, ["setup", "--project-dir", str(tmp_path)])
        second = (tmp_path / ".claude" / "settings.json").read_text()

        assert first == second

    def test_uninstall_removes_hooks(self, tmp_path) -> None:
        runner = CliRunner()
        runner.invoke(main, ["setup", "--project-dir", str(tmp_path)])
        result = runner.invoke(main, ["uninstall", "--project-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "Removed" in result.output

        settings_file = tmp_path / ".claude" / "settings.json"
        # File should be deleted since no other settings remain
        assert not settings_file.exists()

    def test_uninstall_removes_absolute_path_hooks(self, tmp_path) -> None:
        runner = CliRunner()
        with patch("agentlint.cli._resolve_command", return_value="/usr/local/bin/agentlint"):
            runner.invoke(main, ["setup", "--project-dir", str(tmp_path)])
        result = runner.invoke(main, ["uninstall", "--project-dir", str(tmp_path)])

        assert result.exit_code == 0
        settings_file = tmp_path / ".claude" / "settings.json"
        assert not settings_file.exists()

    def test_uninstall_preserves_other_settings(self, tmp_path) -> None:
        settings_file = tmp_path / ".claude" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text(json.dumps({"other": "value", "hooks": {}}))

        runner = CliRunner()
        runner.invoke(main, ["setup", "--project-dir", str(tmp_path)])
        runner.invoke(main, ["uninstall", "--project-dir", str(tmp_path)])

        data = json.loads(settings_file.read_text())
        assert data == {"other": "value"}

    def test_uninstall_noop_when_not_installed(self, tmp_path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["uninstall", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "Removed" in result.output
