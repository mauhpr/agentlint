"""Tests for subagent-transcript-audit rule."""
from __future__ import annotations

import json
import os

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.subagent_transcript_audit import (
    SubagentTranscriptAudit,
    _extract_bash_commands,
    _check_command,
)


def _ctx(
    transcript_path: str | None = None,
    agent_type: str | None = "general-purpose",
    agent_id: str | None = "abc-123",
    session_state: dict | None = None,
) -> RuleContext:
    return RuleContext(
        event=HookEvent.SUB_AGENT_STOP,
        tool_name="",
        tool_input={},
        project_dir="/tmp/project",
        session_state=session_state if session_state is not None else {},
        agent_transcript_path=transcript_path,
        agent_type=agent_type,
        agent_id=agent_id,
    )


def _write_transcript(tmp_path, entries: list[dict]) -> str:
    """Write a JSONL transcript file and return the path."""
    path = str(tmp_path / "transcript.jsonl")
    with open(path, "w") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return path


class TestExtractBashCommands:
    def test_top_level_tool_name(self, tmp_path):
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
        ])
        commands = _extract_bash_commands(path)
        assert commands == ["ls -la"]

    def test_content_block_tool_use(self, tmp_path):
        path = _write_transcript(tmp_path, [
            {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "echo hello"}}]},
        ])
        commands = _extract_bash_commands(path)
        assert commands == ["echo hello"]

    def test_ignores_non_bash_tools(self, tmp_path):
        path = _write_transcript(tmp_path, [
            {"tool_name": "Write", "tool_input": {"file_path": "test.py", "content": "x=1"}},
            {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "test.py"}}]},
        ])
        commands = _extract_bash_commands(path)
        assert commands == []

    def test_multiple_entries(self, tmp_path):
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            {"tool_name": "Bash", "tool_input": {"command": "pwd"}},
            {"tool_name": "Write", "tool_input": {}},
            {"content": [{"type": "tool_use", "name": "Bash", "input": {"command": "echo test"}}]},
        ])
        commands = _extract_bash_commands(path)
        assert commands == ["ls", "pwd", "echo test"]

    def test_empty_transcript(self, tmp_path):
        path = _write_transcript(tmp_path, [])
        commands = _extract_bash_commands(path)
        assert commands == []

    def test_malformed_json_lines_skipped(self, tmp_path):
        path = str(tmp_path / "transcript.jsonl")
        with open(path, "w") as f:
            f.write("not json\n")
            f.write(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}) + "\n")
            f.write("{bad json\n")
        commands = _extract_bash_commands(path)
        assert commands == ["ls"]

    def test_missing_file_returns_empty(self):
        commands = _extract_bash_commands("/nonexistent/path.jsonl")
        assert commands == []

    def test_empty_command_skipped(self, tmp_path):
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": ""}},
            {"tool_name": "Bash", "tool_input": {}},
        ])
        commands = _extract_bash_commands(path)
        assert commands == []


class TestCheckCommand:
    def test_terraform_destroy(self):
        findings = _check_command("terraform destroy -auto-approve")
        assert any("terraform destroy" in label for _, label in findings)

    def test_drop_database(self):
        findings = _check_command("psql -c 'DROP DATABASE mydb'")
        assert any("DROP TABLE/DATABASE" in label for _, label in findings)

    def test_aws_deletion(self):
        findings = _check_command("aws s3 rm s3://bucket --recursive")
        assert any("AWS resource deletion" in label for _, label in findings)

    def test_gcloud_deletion(self):
        findings = _check_command("gcloud compute instances delete my-instance")
        assert any("GCP resource deletion" in label for _, label in findings)

    def test_iptables_flush(self):
        findings = _check_command("iptables -F")
        assert any("iptables flush" in label for _, label in findings)

    def test_git_force_push(self):
        findings = _check_command("git push --force origin main")
        assert any("git force push" in label for _, label in findings)

    def test_safe_command_no_findings(self):
        findings = _check_command("ls -la")
        assert findings == []

    def test_rm_rf(self):
        findings = _check_command("rm -rf /var/data")
        assert any("recursive force delete" in label for _, label in findings)

    def test_kubectl_delete_namespace(self):
        findings = _check_command("kubectl delete namespace production")
        assert any("kubectl delete namespace" in label for _, label in findings)

    def test_production_db_access(self):
        findings = _check_command("psql -h prod-db.example.com -d mydb")
        assert any("production database" in label for _, label in findings)


class TestSubagentTranscriptAudit:
    rule = SubagentTranscriptAudit()

    def test_no_transcript_path_returns_empty(self):
        ctx = _ctx(transcript_path=None)
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_missing_transcript_file_returns_empty(self):
        ctx = _ctx(transcript_path="/nonexistent/file.jsonl")
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_clean_transcript_no_violations(self, tmp_path):
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
            {"tool_name": "Bash", "tool_input": {"command": "cat README.md"}},
        ])
        ctx = _ctx(transcript_path=path)
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_dangerous_command_returns_warning(self, tmp_path):
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": "terraform destroy -auto-approve"}},
        ])
        ctx = _ctx(transcript_path=path)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING
        assert "terraform destroy" in violations[0].message

    def test_multiple_dangerous_commands(self, tmp_path):
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": "terraform destroy"}},
            {"tool_name": "Bash", "tool_input": {"command": "ls -la"}},
            {"tool_name": "Bash", "tool_input": {"command": "aws rds delete-db-instance --db-instance-identifier prod"}},
        ])
        ctx = _ctx(transcript_path=path)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 2  # terraform + aws delete

    def test_records_audit_in_session_state(self, tmp_path):
        session_state: dict = {}
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": "terraform destroy"}},
        ])
        ctx = _ctx(transcript_path=path, session_state=session_state)
        self.rule.evaluate(ctx)

        assert "subagent_audits" in session_state
        audit = session_state["subagent_audits"][0]
        assert audit["agent_type"] == "general-purpose"
        assert audit["commands_count"] == 1
        assert len(audit["findings"]) == 1

    def test_clean_audit_recorded_in_session_state(self, tmp_path):
        session_state: dict = {}
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        ])
        ctx = _ctx(transcript_path=path, session_state=session_state)
        self.rule.evaluate(ctx)

        audit = session_state["subagent_audits"][0]
        assert audit["commands_count"] == 1
        assert audit["findings"] == []

    def test_oversized_transcript_skipped(self, tmp_path):
        """Transcripts over 1MB should be skipped."""
        path = str(tmp_path / "large.jsonl")
        # Create a file just over 1MB
        with open(path, "w") as f:
            # Each line is ~100 bytes, need ~11000 lines for >1MB
            for i in range(11000):
                f.write(json.dumps({"tool_name": "Bash", "tool_input": {"command": f"echo {i} " + "x" * 80}}) + "\n")

        assert os.path.getsize(path) > 1_048_576

        ctx = _ctx(transcript_path=path)
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_empty_transcript_no_violations(self, tmp_path):
        path = _write_transcript(tmp_path, [])
        session_state: dict = {}
        ctx = _ctx(transcript_path=path, session_state=session_state)
        violations = self.rule.evaluate(ctx)
        assert violations == []
        # Should still record the audit
        assert session_state["subagent_audits"][0]["commands_count"] == 0

    def test_truncates_long_commands_in_message(self, tmp_path):
        long_cmd = "terraform destroy " + "x" * 200
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": long_cmd}},
        ])
        ctx = _ctx(transcript_path=path)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "..." in violations[0].message
        assert len(violations[0].message) < 300

    def test_rule_id(self):
        assert self.rule.id == "subagent-transcript-audit"

    def test_rule_pack(self):
        assert self.rule.pack == "autopilot"

    def test_rule_events(self):
        assert self.rule.events == [HookEvent.SUB_AGENT_STOP]

    def test_matches_subagent_stop_event(self):
        assert self.rule.matches_event(HookEvent.SUB_AGENT_STOP)

    def test_does_not_match_other_events(self):
        assert not self.rule.matches_event(HookEvent.PRE_TOOL_USE)
        assert not self.rule.matches_event(HookEvent.SUB_AGENT_START)

    def test_content_null_does_not_crash(self, tmp_path):
        """JSONL entry with "content": null must not raise TypeError."""
        path = _write_transcript(tmp_path, [
            {"content": None},
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        ])
        commands = _extract_bash_commands(path)
        assert commands == ["ls"]

    def test_content_null_in_dangerous_transcript(self, tmp_path):
        """Null content entries are skipped; dangerous commands still detected."""
        path = _write_transcript(tmp_path, [
            {"content": None},
            {"tool_name": "Bash", "tool_input": {"command": "terraform destroy"}},
            {"content": None},
        ])
        ctx = _ctx(transcript_path=path)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "terraform destroy" in violations[0].message

    def test_oversized_line_skipped(self, tmp_path):
        """Individual JSONL lines over 100KB should be skipped."""
        huge_cmd = "echo " + "x" * 110_000
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": huge_cmd}},
            {"tool_name": "Bash", "tool_input": {"command": "terraform destroy"}},
        ])
        ctx = _ctx(transcript_path=path)
        violations = self.rule.evaluate(ctx)
        # The oversized line is skipped, but terraform destroy is still caught
        assert len(violations) == 1
        assert "terraform destroy" in violations[0].message

    def test_heroku_destroy_detected(self, tmp_path):
        """Heroku apps:destroy should be caught by shared patterns."""
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": "heroku apps:destroy --app my-app --confirm my-app"}},
        ])
        ctx = _ctx(transcript_path=path)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "Heroku" in violations[0].message

    def test_azure_deletion_detected(self, tmp_path):
        """Azure delete commands should be caught by shared patterns."""
        path = _write_transcript(tmp_path, [
            {"tool_name": "Bash", "tool_input": {"command": "az group delete --name my-rg --yes"}},
        ])
        ctx = _ctx(transcript_path=path)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "Azure" in violations[0].message
