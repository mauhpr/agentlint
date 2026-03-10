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
        """Write with an API key should be blocked via deny protocol (exit 0)."""
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
        # PreToolUse blocking uses exit 0 + hookSpecificOutput deny protocol
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "no-secrets" in parsed["hookSpecificOutput"]["permissionDecisionReason"]

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


class TestCheckNewEvents:
    """New v0.4.0 hook events pass through gracefully."""

    def test_user_prompt_submit_passthrough(self, tmp_path) -> None:
        payload = json.dumps({"prompt": "delete everything"})
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "UserPromptSubmit", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0

    def test_subagent_stop_passthrough(self, tmp_path) -> None:
        payload = json.dumps({"subagent_output": "done"})
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "SubagentStop", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0

    def test_notification_passthrough(self, tmp_path) -> None:
        payload = json.dumps({"notification_type": "warning"})
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "Notification", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0

    def test_session_end_passthrough(self, tmp_path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "SessionEnd", "--project-dir", str(tmp_path)],
            input="{}",
        )
        assert result.exit_code == 0

    def test_pre_compact_passthrough(self, tmp_path) -> None:
        payload = json.dumps({"compact_source": "auto"})
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreCompact", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0

    def test_post_tool_use_failure_passthrough(self, tmp_path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PostToolUseFailure", "--project-dir", str(tmp_path)],
            input="{}",
        )
        assert result.exit_code == 0

    def test_all_new_events_accept_empty_input(self, tmp_path) -> None:
        """Every new event should accept empty JSON input without crashing."""
        new_events = [
            "SessionEnd", "UserPromptSubmit", "SubagentStart", "SubagentStop",
            "Notification", "PreCompact", "PostToolUseFailure", "PermissionRequest",
            "ConfigChange", "WorktreeCreate", "WorktreeRemove", "TeammateIdle",
            "TaskCompleted",
        ]
        runner = CliRunner()
        for event in new_events:
            result = runner.invoke(
                main,
                ["check", "--event", event, "--project-dir", str(tmp_path)],
                input="{}",
            )
            assert result.exit_code == 0, f"Event {event} failed with exit code {result.exit_code}"


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
        assert "3 rules total" in result.output

    def test_list_rules_autopilot_pack(self) -> None:
        """list-rules --pack autopilot should show only autopilot rules."""
        runner = CliRunner()
        result = runner.invoke(main, ["list-rules", "--pack", "autopilot"])
        assert result.exit_code == 0
        assert "cloud-resource-deletion" in result.output
        assert "network-firewall-guard" in result.output
        assert "docker-volume-guard" in result.output
        assert "18 rules total" in result.output

    def test_list_rules_universal_pack(self) -> None:
        """list-rules --pack universal should show only universal rules."""
        runner = CliRunner()
        result = runner.invoke(main, ["list-rules", "--pack", "universal"])
        assert result.exit_code == 0
        assert "no-secrets" in result.output
        assert "17 rules total" in result.output

    def test_list_rules_quality_pack(self) -> None:
        """list-rules --pack quality should show only quality rules."""
        runner = CliRunner()
        result = runner.invoke(main, ["list-rules", "--pack", "quality"])
        assert result.exit_code == 0
        assert "commit-message-format" in result.output
        assert "no-dead-imports" in result.output
        assert "no-error-handling-removal" in result.output
        assert "4 rules total" in result.output

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


class TestStatusCommand:
    def test_status_outputs_version_and_rules(self, tmp_path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "AgentLint" in result.output
        assert "Rules:" in result.output
        assert "Packs:" in result.output

    def test_status_shows_pack_names(self, tmp_path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["status", "--project-dir", str(tmp_path)])
        assert "universal" in result.output


class TestDoctorCommand:
    def test_doctor_all_checks_pass(self, tmp_path) -> None:
        # Create config and hooks so checks pass
        (tmp_path / "agentlint.yml").write_text("stack: auto\n")
        settings_dir = tmp_path / ".claude"
        settings_dir.mkdir()
        (settings_dir / "settings.json").write_text(
            json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"command": "agentlint check"}]}]}})
        )
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert "All checks passed" in result.output

    def test_doctor_warns_missing_config(self, tmp_path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--project-dir", str(tmp_path)])
        assert "not found" in result.output

    def test_doctor_warns_missing_hooks(self, tmp_path) -> None:
        (tmp_path / "agentlint.yml").write_text("stack: auto\n")
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--project-dir", str(tmp_path)])
        assert "not installed" in result.output

    def test_doctor_checks_python_version(self, tmp_path) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["doctor", "--project-dir", str(tmp_path)])
        assert "Python:" in result.output


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

    def test_report_includes_session_tracked_files(self, tmp_path, monkeypatch) -> None:
        """Report should count files tracked during the session, not just git diff."""
        from agentlint.session import save_session

        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "test-report-files")

        # Simulate session state with files_touched (as check command would populate)
        save_session({"files_touched": ["/project/a.py", "/project/b.py", "/project/c.py"]})

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--project-dir", str(tmp_path)],
            input="{}",
        )

        assert result.exit_code == 0
        # Should show at least the 3 session-tracked files
        parsed = json.loads(result.output)
        assert "Files changed: 3" in parsed["systemMessage"]

    def test_check_tracks_files_touched_in_session(self, tmp_path, monkeypatch) -> None:
        """check should accumulate file paths in session state files_touched."""
        from agentlint.session import load_session

        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "test-track-files")

        # Create a file so the tool_input file_path resolves
        target = tmp_path / "test.py"
        target.write_text("x = 1\n")

        payload = json.dumps({
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": "x = 2\n",
            },
        })
        runner = CliRunner()
        runner.invoke(
            main,
            ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
            input=payload,
        )

        session = load_session()
        assert str(target) in session.get("files_touched", [])


class TestSubagentFieldMapping:
    """v0.8.0 — subagent field mapping in CLI."""

    def test_subagent_start_passthrough(self, tmp_path) -> None:
        """SubagentStart event should accept agent fields."""
        payload = json.dumps({
            "agent_type": "general-purpose",
            "agent_id": "abc-123",
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "SubagentStart", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0

    def test_subagent_stop_reads_last_assistant_message(self, tmp_path) -> None:
        """SubagentStop should read last_assistant_message field."""
        payload = json.dumps({
            "last_assistant_message": "I completed the task",
            "agent_type": "general-purpose",
            "agent_id": "abc-123",
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "SubagentStop", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0

    def test_subagent_stop_falls_back_to_subagent_output(self, tmp_path) -> None:
        """SubagentStop should fall back to subagent_output for backward compat."""
        payload = json.dumps({
            "subagent_output": "legacy field",
            "agent_type": "general-purpose",
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "SubagentStop", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0

    def test_subagent_stop_with_transcript_path(self, tmp_path) -> None:
        """SubagentStop should accept agent_transcript_path."""
        payload = json.dumps({
            "agent_transcript_path": "/tmp/transcript.jsonl",
            "agent_type": "general-purpose",
            "agent_id": "abc-123",
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "SubagentStop", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0

    def test_subagent_start_with_autopilot_returns_context(self, tmp_path) -> None:
        """SubagentStart with autopilot enabled should return additionalContext."""
        config_path = tmp_path / "agentlint.yml"
        config_path.write_text("stack: auto\npacks:\n  - universal\n  - autopilot\n")

        payload = json.dumps({
            "agent_type": "general-purpose",
            "agent_id": "abc-123",
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "SubagentStart", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "hookSpecificOutput" in parsed
        assert parsed["hookSpecificOutput"]["hookEventName"] == "SubagentStart"
        assert "SAFETY NOTICE" in parsed["hookSpecificOutput"]["additionalContext"]


class TestReportCircuitBreaker:
    def test_report_shows_cb_activity(self, tmp_path, monkeypatch) -> None:
        """Report should include circuit breaker data from session."""
        from agentlint.session import save_session

        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "test-cb-report")

        save_session({
            "circuit_breaker": {
                "no-destructive-commands": {
                    "fire_count": 5,
                    "state": "degraded",
                }
            }
        })

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--project-dir", str(tmp_path)],
            input="{}",
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "Circuit Breaker" in parsed["systemMessage"]
        assert "no-destructive-commands" in parsed["systemMessage"]


class TestRecordingsCommands:
    def test_recordings_list_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(main, ["recordings", "list"])
        assert result.exit_code == 0
        assert "No recordings found" in result.output

    def test_recordings_list_shows_entries(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        from agentlint.recorder import append_event
        append_event({"ts": 1.0, "event": "PreToolUse", "tool_name": "Bash"}, "test-sess")

        runner = CliRunner()
        result = runner.invoke(main, ["recordings", "list"])
        assert result.exit_code == 0
        assert "test-sess" in result.output
        assert "1 recording(s)" in result.output

    def test_recordings_show(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        from agentlint.recorder import append_event
        append_event({
            "ts": 1710000000.0, "event": "PreToolUse",
            "tool_name": "Bash", "violations": [],
            "tool_summary": {"command": "ls -la", "file_path": None, "content_length": None},
        }, "show-sess")

        runner = CliRunner()
        result = runner.invoke(main, ["recordings", "show", "show-sess"])
        assert result.exit_code == 0
        assert "PreToolUse" in result.output
        assert "Bash" in result.output
        assert "$ ls -la" in result.output

    def test_recordings_stats(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        from agentlint.recorder import append_event
        for i in range(5):
            append_event({
                "ts": float(i), "event": "PreToolUse",
                "tool_name": "Bash", "violations": [],
            }, "stats-sess")

        runner = CliRunner()
        result = runner.invoke(main, ["recordings", "stats"])
        assert result.exit_code == 0
        assert "Bash" in result.output
        assert "Events: 5" in result.output

    def test_recordings_clear(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        from agentlint.recorder import append_event
        append_event({"ts": 1.0}, "to-delete")

        runner = CliRunner()
        result = runner.invoke(main, ["recordings", "clear"], input="y\n")
        assert result.exit_code == 0
        assert "Removed 1 recording(s)" in result.output

    def test_recordings_stats_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(main, ["recordings", "stats"])
        assert result.exit_code == 0
        assert "No recordings found" in result.output

    def test_recordings_show_unknown_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(main, ["recordings", "show", "nonexistent-key"])
        assert result.exit_code == 0
        assert "No recordings found" in result.output

    def test_recordings_show_agent_summary(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        from agentlint.recorder import append_event
        append_event({
            "ts": 1710000000.0, "event": "PreToolUse",
            "tool_name": "Agent", "violations": [],
            "tool_summary": {
                "command": None, "file_path": None, "content_length": None,
                "subagent_type": "Explore", "description": "Find auth code",
            },
        }, "agent-sess")

        runner = CliRunner()
        result = runner.invoke(main, ["recordings", "show", "agent-sess"])
        assert result.exit_code == 0
        assert "[Explore]" in result.output
        assert "Find auth code" in result.output

    def test_recordings_show_web_summary(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        from agentlint.recorder import append_event
        append_event({
            "ts": 1710000000.0, "event": "PreToolUse",
            "tool_name": "WebSearch", "violations": [],
            "tool_summary": {
                "command": None, "file_path": None, "content_length": None,
                "query": "python asyncio tutorial",
            },
        }, "web-sess")

        runner = CliRunner()
        result = runner.invoke(main, ["recordings", "show", "web-sess"])
        assert result.exit_code == 0
        assert "python asyncio tutorial" in result.output

    def test_recordings_show_violations_only(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        from agentlint.recorder import append_event
        # Clean event
        append_event({
            "ts": 1.0, "event": "PreToolUse",
            "tool_name": "Bash", "violations": [],
            "tool_summary": {"command": "ls", "file_path": None, "content_length": None},
        }, "filter-sess")
        # Event with violation
        append_event({
            "ts": 2.0, "event": "PreToolUse",
            "tool_name": "Write", "violations": [{"rule_id": "no-secrets", "severity": "error"}],
            "tool_summary": {"command": None, "file_path": "/bad.py", "content_length": 100},
        }, "filter-sess")

        runner = CliRunner()
        # Without filter: both events shown
        result = runner.invoke(main, ["recordings", "show", "filter-sess"])
        assert "2 event(s) shown (2 total)" in result.output
        assert "Violation summary:" in result.output
        assert "no-secrets" in result.output

        # With --violations-only: only the violation event shown
        result = runner.invoke(main, ["recordings", "show", "--violations-only", "filter-sess"])
        assert "1 event(s) shown (2 total)" in result.output
        assert "Write" in result.output
        assert "$ ls" not in result.output

    def test_recordings_show_no_violation_summary_when_clean(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        from agentlint.recorder import append_event
        append_event({
            "ts": 1.0, "event": "PreToolUse",
            "tool_name": "Bash", "violations": [],
            "tool_summary": {"command": "ls", "file_path": None, "content_length": None},
        }, "clean-sess")

        runner = CliRunner()
        result = runner.invoke(main, ["recordings", "show", "clean-sess"])
        assert "Violation summary:" not in result.output


class TestRecordingIntegration:
    """Integration tests: recording fires (or doesn't) during check/report."""

    def test_check_records_when_enabled(self, tmp_path, monkeypatch):
        """check with recording enabled should write a .jsonl file."""
        rec_dir = tmp_path / "recordings"
        monkeypatch.setenv("AGENTLINT_RECORDING", "1")
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(rec_dir))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "rec-integration-test")
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path / "cache"))

        payload = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "ls -la"},
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0

        from agentlint.recorder import load_recording
        recording = load_recording("rec-integration-test")
        assert len(recording) == 1
        assert recording[0]["tool_name"] == "Bash"
        assert recording[0]["v"] == 1
        assert recording[0]["event"] == "PreToolUse"

    def test_check_does_not_record_when_disabled(self, tmp_path, monkeypatch):
        """check with recording disabled should NOT create any .jsonl files."""
        rec_dir = tmp_path / "recordings"
        monkeypatch.delenv("AGENTLINT_RECORDING", raising=False)
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(rec_dir))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "no-rec-test")
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path / "cache"))

        payload = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "echo hello"},
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
            input=payload,
        )
        assert result.exit_code == 0

        # No recording files should exist
        if rec_dir.exists():
            assert list(rec_dir.glob("*.jsonl")) == []

    def test_report_records_when_enabled(self, tmp_path, monkeypatch):
        """report with recording enabled should write a Stop event."""
        rec_dir = tmp_path / "recordings"
        monkeypatch.setenv("AGENTLINT_RECORDING", "1")
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(rec_dir))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "rec-report-test")
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path / "cache"))

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--project-dir", str(tmp_path)],
            input="{}",
        )
        assert result.exit_code == 0

        from agentlint.recorder import load_recording
        recording = load_recording("rec-report-test")
        assert len(recording) == 1
        assert recording[0]["event"] == "Stop"
        assert recording[0]["v"] == 1
