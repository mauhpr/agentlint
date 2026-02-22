"""Tests for AgentLint CLI entry point."""
from __future__ import annotations

import json
import os

from click.testing import CliRunner

from agentlint.cli import main


class TestCheckCommand:
    def test_check_with_empty_input(self, tmp_path) -> None:
        """Empty JSON input should produce no violations and exit 0."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
            input="{}",
        )
        assert result.exit_code == 0

    def test_check_blocks_secrets(self, tmp_path) -> None:
        """Write with an API key should be blocked (exit code 2)."""
        payload = json.dumps({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "config.py",
                "content": 'API_KEY = "sk_live_abc123def456ghi789"',
            },
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 2
        assert "no-secrets" in result.output

    def test_check_passes_clean_code(self, tmp_path) -> None:
        """Write with clean code should pass (exit code 0)."""
        payload = json.dumps({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "hello.py",
                "content": "def hello():\n    return 'world'\n",
            },
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0


class TestInitCommand:
    def test_init_creates_config(self, tmp_path) -> None:
        """init should create agentlint.yml in the project directory."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--project-dir", str(tmp_path)])

        assert result.exit_code == 0
        config_path = tmp_path / "agentlint.yml"
        assert config_path.exists()
        assert "agentlint" in config_path.read_text().lower()

    def test_init_detects_universal(self, tmp_path) -> None:
        """init should always include universal pack."""
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--project-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "universal" in result.output.lower()


class TestCheckErrorPaths:
    def test_invalid_event_value(self, tmp_path) -> None:
        """Invalid --event value should cause a ValueError."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "InvalidEvent", "--project-dir", str(tmp_path)],
            input="{}",
        )
        assert result.exit_code != 0

    def test_malformed_json_stdin(self, tmp_path) -> None:
        """Malformed JSON should not crash — treated as empty input."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
            input="not json at all {{{",
        )
        assert result.exit_code == 0

    def test_binary_like_content(self, tmp_path) -> None:
        """Binary-like content in stdin should not crash."""
        payload = json.dumps({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "test.bin",
                "content": "\x00\x01\x02\x03binary content\xff\xfe",
            },
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0

    def test_missing_event_flag(self, tmp_path) -> None:
        """--event is required."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--project-dir", str(tmp_path)],
            input="{}",
        )
        assert result.exit_code != 0


class TestCheckEdgeCases:
    def test_empty_stdin_check(self, tmp_path) -> None:
        """Empty stdin (EOFError) on check should not crash."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
            input="",
        )
        assert result.exit_code == 0

    def test_project_dir_from_env(self, tmp_path, monkeypatch) -> None:
        """CLAUDE_PROJECT_DIR env var is used when --project-dir not provided."""
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreToolUse"],
            input="{}",
        )
        assert result.exit_code == 0

    def test_path_traversal_blocked(self, tmp_path) -> None:
        """File path outside project dir should be blocked in PostToolUse."""
        payload = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": "/etc/passwd"},
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PostToolUse", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0


class TestListRulesCommand:
    def test_list_all_rules(self) -> None:
        """list-rules should output a table of all rules."""
        runner = CliRunner()
        result = runner.invoke(main, ["list-rules"])
        assert result.exit_code == 0
        assert "no-secrets" in result.output
        assert "no-env-commit" in result.output
        assert "rules total" in result.output

    def test_list_rules_security_pack(self) -> None:
        """list-rules --pack security should show only security rules."""
        runner = CliRunner()
        result = runner.invoke(main, ["list-rules", "--pack", "security"])
        assert result.exit_code == 0
        assert "no-bash-file-write" in result.output
        assert "no-network-exfil" in result.output
        assert "2 rules total" in result.output

    def test_list_rules_universal_pack(self) -> None:
        """list-rules --pack universal should show only universal rules."""
        runner = CliRunner()
        result = runner.invoke(main, ["list-rules", "--pack", "universal"])
        assert result.exit_code == 0
        assert "no-secrets" in result.output
        assert "13 rules total" in result.output

    def test_list_rules_unknown_pack(self) -> None:
        """list-rules with unknown pack should show no rules."""
        runner = CliRunner()
        result = runner.invoke(main, ["list-rules", "--pack", "nonexistent"])
        assert result.exit_code == 0
        assert "No rules found" in result.output

    def test_list_rules_columns(self) -> None:
        """list-rules should show Rule ID, Pack, Event, Severity, Description columns."""
        runner = CliRunner()
        result = runner.invoke(main, ["list-rules"])
        assert "Rule ID" in result.output
        assert "Pack" in result.output
        assert "Event" in result.output
        assert "Severity" in result.output
        assert "Description" in result.output


class TestReportCommand:
    def test_report_outputs_summary(self) -> None:
        """report should output JSON with AgentLint session summary."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--project-dir", "/tmp"],
            input="{}",
        )

        assert result.exit_code == 0
        assert "AgentLint" in result.output

    def test_empty_stdin_report(self) -> None:
        """Empty stdin (EOFError) on report should not crash."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--project-dir", "/tmp"],
            input="",
        )
        assert result.exit_code == 0
        assert "AgentLint" in result.output
