"""Tests for shared adapter utilities and auto-detection."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agentlint.adapters._utils import (
    is_agentlint_flat_entry,
    is_agentlint_nested_entry,
    read_json_config,
    resolve_command,
    write_json_config,
)
from agentlint.adapters.base import AgentAdapter


class TestResolveCommand:
    """Test the multi-location probe chain in resolve_command()."""

    def _no_which(self):
        return patch("agentlint.adapters._utils.shutil.which", return_value=None)

    def test_step1_which_succeeds(self) -> None:
        with patch("agentlint.adapters._utils.shutil.which", return_value="/usr/local/bin/agentlint"):
            result = resolve_command()
        assert result == "/usr/local/bin/agentlint"

    def test_step2_pipx_location(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        pipx_bin = tmp_path / ".local" / "bin" / "agentlint"
        pipx_bin.parent.mkdir(parents=True)
        pipx_bin.write_text("#!/bin/sh\n")

        with self._no_which():
            result = resolve_command()
        assert result == str(pipx_bin)

    def test_step5_python_m_fallback(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        with self._no_which(), patch("agentlint.adapters._utils.sysconfig.get_path", return_value=None):
            result = resolve_command()
        assert "python" in result and "-m agentlint" in result

    def test_returns_string_with_agentlint(self) -> None:
        result = resolve_command()
        assert isinstance(result, str)
        assert "agentlint" in result


class TestReadJsonConfig:
    def test_reads_valid_json(self, tmp_path) -> None:
        f = tmp_path / "settings.json"
        f.write_text('{"hooks": {}}')
        assert read_json_config(f) == {"hooks": {}}

    def test_returns_empty_dict_for_missing_file(self, tmp_path) -> None:
        f = tmp_path / "nonexistent.json"
        assert read_json_config(f) == {}

    def test_returns_none_for_invalid_json(self, tmp_path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("{not valid json")
        assert read_json_config(f) is None


class TestWriteJsonConfig:
    def test_writes_json_with_indent(self, tmp_path) -> None:
        f = tmp_path / "out.json"
        write_json_config(f, {"key": "value"})
        content = f.read_text()
        assert '"key": "value"' in content
        assert content.startswith("{\n")
        assert content.endswith("}\n")

    def test_creates_parent_dirs(self, tmp_path) -> None:
        f = tmp_path / ".claude" / "settings.json"
        write_json_config(f, {"a": 1})
        assert f.exists()
        assert json.loads(f.read_text()) == {"a": 1}


class TestIsAgentlintNestedEntry:
    def test_matches_v2_marker(self) -> None:
        entry = {"hooks": [{"type": "command", "_agentlint": "v2", "command": "agentlint check"}]}
        assert is_agentlint_nested_entry(entry) is True

    def test_matches_legacy_command_pattern(self) -> None:
        entry = {"hooks": [{"type": "command", "command": "agentlint check --event PreToolUse"}]}
        assert is_agentlint_nested_entry(entry) is True

    def test_rejects_false_positive_substring(self) -> None:
        # "agentlint" appears in command but not as a generated hook pattern
        entry = {"hooks": [{"type": "command", "command": "echo agentlint is great"}]}
        assert is_agentlint_nested_entry(entry) is False

    def test_rejects_wrapper_command(self) -> None:
        entry = {"hooks": [{"type": "command", "command": "/home/user/.local/bin/agentlint-wrapper check"}]}
        assert is_agentlint_nested_entry(entry) is False

    def test_rejects_third_party_entry(self) -> None:
        entry = {"hooks": [{"type": "command", "command": "my-other-tool check"}]}
        assert is_agentlint_nested_entry(entry) is False

    def test_handles_empty_hooks(self) -> None:
        assert is_agentlint_nested_entry({}) is False
        assert is_agentlint_nested_entry({"hooks": []}) is False


class TestIsAgentlintFlatEntry:
    def test_matches_v2_marker(self) -> None:
        entry = {"_agentlint": "v2", "command": "agentlint check --event preToolUse"}
        assert is_agentlint_flat_entry(entry) is True

    def test_matches_legacy_command_pattern(self) -> None:
        entry = {"command": "agentlint check --event preToolUse"}
        assert is_agentlint_flat_entry(entry) is True

    def test_rejects_false_positive_substring(self) -> None:
        entry = {"command": "echo agentlint is great"}
        assert is_agentlint_flat_entry(entry) is False

    def test_rejects_third_party_entry(self) -> None:
        entry = {"command": "my-other-tool check"}
        assert is_agentlint_flat_entry(entry) is False


class TestClaudeAdapter:
    def test_resolves_project_dir_from_agentlint_env(self, monkeypatch) -> None:
        from agentlint.adapters.claude import ClaudeAdapter

        monkeypatch.setenv("AGENTLINT_PROJECT_DIR", "/my/agentlint/project")
        adapter = ClaudeAdapter()
        assert adapter.resolve_project_dir() == "/my/agentlint/project"

    def test_resolves_session_key_from_env(self, monkeypatch) -> None:
        from agentlint.adapters.claude import ClaudeAdapter

        monkeypatch.setenv("AGENTLINT_SESSION_ID", "session-123")
        adapter = ClaudeAdapter()
        assert adapter.resolve_session_key() == "session-123"

    def test_normalize_unknown_tool(self) -> None:
        from agentlint.adapters.claude import ClaudeAdapter

        adapter = ClaudeAdapter()
        assert adapter.normalize_tool_name("unknown_tool") == "unknown"

    def test_build_rule_context_defaults(self) -> None:
        from agentlint.adapters.claude import ClaudeAdapter
        from agentlint.models import AgentEvent

        adapter = ClaudeAdapter()
        ctx = adapter.build_rule_context(AgentEvent.PRE_TOOL_USE, {"event": "PreToolUse"}, "/tmp", {})
        assert ctx.tool_input == {}
        assert ctx.tool_name == ""

    def test_uninstall_preserves_event_with_remaining_hooks(self, tmp_path) -> None:
        from agentlint.adapters.claude import ClaudeAdapter

        settings_file = tmp_path / ".claude" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        existing = {
            "hooks": {
                "PreToolUse": [
                    {"matcher": "Bash", "hooks": [{"command": "echo hello"}]},
                    {"matcher": "Write", "hooks": [{"command": "agentlint check --event PreToolUse --adapter claude", "_agentlint": "v2"}]},
                ],
                "PostToolUse": [
                    {"matcher": "Write", "hooks": [{"command": "agentlint check --event PostToolUse --adapter claude", "_agentlint": "v2"}]},
                ]
            }
        }
        settings_file.write_text(json.dumps(existing))

        adapter = ClaudeAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        data = json.loads(settings_file.read_text())
        assert "PreToolUse" in data["hooks"]
        assert len(data["hooks"]["PreToolUse"]) == 1
        assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo hello"
        assert "PostToolUse" not in data["hooks"]


class TestCorruptedConfigProtection:
    """Verify uninstall_hooks does not delete corrupted config files."""

    def test_claude_preserves_corrupted_settings(self, tmp_path) -> None:
        from agentlint.adapters.claude import ClaudeAdapter

        settings_file = tmp_path / ".claude" / "settings.json"
        settings_file.parent.mkdir(parents=True)
        settings_file.write_text("{not valid json")

        adapter = ClaudeAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        # Corrupted file should still exist
        assert settings_file.exists()
        assert "{not valid json" in settings_file.read_text()

    def test_cursor_preserves_corrupted_hooks(self, tmp_path) -> None:
        from agentlint.adapters.cursor import CursorAdapter

        hooks_file = tmp_path / ".cursor" / "hooks.json"
        hooks_file.parent.mkdir(parents=True)
        hooks_file.write_text("{not valid json")

        adapter = CursorAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        assert hooks_file.exists()

    def test_kimi_preserves_corrupted_toml(self, tmp_path) -> None:
        from agentlint.adapters.kimi import KimiAdapter

        config_file = tmp_path / ".kimi" / "config.toml"
        config_file.parent.mkdir(parents=True)
        config_file.write_text("[[hooks\nnot valid toml")

        adapter = KimiAdapter()
        adapter.uninstall_hooks(str(tmp_path), scope="project")

        assert config_file.exists()


class TestAdapterRegistry:
    def test_get_adapter_returns_instance(self) -> None:
        from agentlint.adapters import get_adapter

        adapter = get_adapter("claude")
        assert isinstance(adapter, AgentAdapter)
        assert adapter.platform_name == "claude"

    def test_get_adapter_all_platforms(self) -> None:
        from agentlint.adapters import get_adapter

        for name in ("claude", "cursor", "kimi", "grok", "gemini", "codex", "continue", "openai", "mcp", "generic"):
            adapter = get_adapter(name)
            assert isinstance(adapter, AgentAdapter)
            assert adapter.platform_name == name

    def test_get_adapter_unknown_raises(self) -> None:
        from agentlint.adapters import get_adapter

        with pytest.raises(ValueError, match="Unknown adapter"):
            get_adapter("nonexistent")
