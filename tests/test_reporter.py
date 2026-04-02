"""Tests for agentlint.reporter."""
from __future__ import annotations

import json

import pytest

from agentlint.models import Severity, Violation
from agentlint.reporter import Reporter


def _make_violation(
    rule_id: str = "TEST001",
    message: str = "Test violation",
    severity: Severity = Severity.WARNING,
    suggestion: str | None = None,
) -> Violation:
    return Violation(
        rule_id=rule_id,
        message=message,
        severity=severity,
        suggestion=suggestion,
    )


class TestFormatHookOutput:
    def test_no_violations_returns_none(self) -> None:
        reporter = Reporter(violations=[])
        assert reporter.format_hook_output() is None

    def test_warnings_produce_system_message(self) -> None:
        violations = [_make_violation(rule_id="WARN01", severity=Severity.WARNING)]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output()
        assert output is not None

        parsed = json.loads(output)
        assert "systemMessage" in parsed
        assert "WARN01" in parsed["systemMessage"]

    def test_format_hook_output_includes_suggestion(self) -> None:
        violations = [
            _make_violation(
                rule_id="SUG01",
                severity=Severity.WARNING,
                suggestion="Try doing X instead",
            )
        ]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output()
        assert output is not None

        parsed = json.loads(output)
        assert "Try doing X instead" in parsed["systemMessage"]


class TestPreToolUseDenyProtocol:
    """Test the hookSpecificOutput deny protocol for PreToolUse blocking."""

    def test_pretooluse_error_uses_deny_protocol(self) -> None:
        """PreToolUse ERROR violations should use permissionDecision=deny."""
        violations = [_make_violation(rule_id="no-secrets", severity=Severity.ERROR, message="Secret detected")]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output(event="PreToolUse")
        assert output is not None

        parsed = json.loads(output)
        assert "hookSpecificOutput" in parsed
        hook_output = parsed["hookSpecificOutput"]
        assert hook_output["hookEventName"] == "PreToolUse"
        assert hook_output["permissionDecision"] == "deny"
        assert "no-secrets" in hook_output["permissionDecisionReason"]
        assert "Secret detected" in hook_output["permissionDecisionReason"]

    def test_pretooluse_error_includes_suggestion_in_reason(self) -> None:
        violations = [_make_violation(
            severity=Severity.ERROR,
            message="Bad thing",
            suggestion="Do the good thing instead",
        )]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output(event="PreToolUse")
        parsed = json.loads(output)
        assert "Do the good thing instead" in parsed["hookSpecificOutput"]["permissionDecisionReason"]

    def test_pretooluse_warning_uses_additional_context(self) -> None:
        """PreToolUse WARNING violations should use additionalContext (agent sees it)."""
        violations = [_make_violation(severity=Severity.WARNING, rule_id="WARN01")]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output(event="PreToolUse")
        parsed = json.loads(output)
        assert "hookSpecificOutput" in parsed
        assert "WARN01" in parsed["hookSpecificOutput"]["additionalContext"]
        assert "systemMessage" not in parsed

    def test_pretooluse_error_includes_warnings_in_reason(self) -> None:
        """When blocking, warnings should be included in the deny reason."""
        violations = [
            _make_violation(rule_id="ERR01", severity=Severity.ERROR, message="Blocked"),
            _make_violation(rule_id="WARN01", severity=Severity.WARNING, message="Also bad"),
        ]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output(event="PreToolUse")
        parsed = json.loads(output)
        reason = parsed["hookSpecificOutput"]["permissionDecisionReason"]
        assert "ERR01" in reason
        assert "WARN01" in reason

    def test_posttooluse_error_uses_additional_context_and_decision(self) -> None:
        """PostToolUse errors should use additionalContext + decision block."""
        violations = [_make_violation(severity=Severity.ERROR, rule_id="ERR01")]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output(event="PostToolUse")
        parsed = json.loads(output)
        assert "hookSpecificOutput" in parsed
        assert "ERR01" in parsed["hookSpecificOutput"]["additionalContext"]
        assert parsed["decision"] == "block"
        assert "ERR01" in parsed["reason"]

    def test_posttooluse_warning_uses_decision_block(self) -> None:
        """PostToolUse WARNING uses decision: block + reason for strong advisory."""
        violations = [_make_violation(severity=Severity.WARNING, rule_id="WARN01", message="Fix this")]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output(event="PostToolUse")
        parsed = json.loads(output)
        assert parsed["decision"] == "block"
        assert "WARN01" in parsed["reason"]
        assert "WARN01" in parsed["hookSpecificOutput"]["additionalContext"]

    def test_posttooluse_info_uses_additional_context_only(self) -> None:
        """PostToolUse INFO uses additionalContext without decision block."""
        violations = [_make_violation(severity=Severity.INFO, rule_id="INFO01")]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output(event="PostToolUse")
        parsed = json.loads(output)
        assert "hookSpecificOutput" in parsed
        assert "INFO01" in parsed["hookSpecificOutput"]["additionalContext"]
        assert "decision" not in parsed

    def test_posttooluse_warning_and_info_combined(self) -> None:
        """Both WARNING and INFO in PostToolUse — decision block for warning, both in context."""
        violations = [
            _make_violation(severity=Severity.WARNING, rule_id="WARN01"),
            _make_violation(severity=Severity.INFO, rule_id="INFO01"),
        ]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output(event="PostToolUse")
        parsed = json.loads(output)
        context = parsed["hookSpecificOutput"]["additionalContext"]
        assert "WARN01" in context
        assert "INFO01" in context
        assert parsed["decision"] == "block"
        # reason only includes warnings, not infos
        assert "WARN01" in parsed["reason"]

    def test_posttooluse_includes_suggestion_in_context(self) -> None:
        violations = [_make_violation(
            severity=Severity.WARNING,
            suggestion="Try this approach",
        )]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output(event="PostToolUse")
        parsed = json.loads(output)
        assert "Try this approach" in parsed["hookSpecificOutput"]["additionalContext"]

    def test_other_events_still_use_system_message(self) -> None:
        """Events without additionalContext support fall back to systemMessage."""
        violations = [_make_violation(severity=Severity.WARNING, rule_id="WARN01")]
        reporter = Reporter(violations=violations)

        # Stop event doesn't support additionalContext
        output = reporter.format_hook_output(event="Stop")
        parsed = json.loads(output)
        assert "systemMessage" in parsed
        assert "WARN01" in parsed["systemMessage"]

    def test_posttooluse_failure_uses_additional_context(self) -> None:
        """PostToolUseFailure should use same path as PostToolUse."""
        violations = [_make_violation(severity=Severity.WARNING, rule_id="WARN01")]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output(event="PostToolUseFailure")
        parsed = json.loads(output)
        assert "hookSpecificOutput" in parsed
        assert parsed["hookSpecificOutput"]["hookEventName"] == "PostToolUseFailure"
        assert "WARN01" in parsed["hookSpecificOutput"]["additionalContext"]
        assert parsed["decision"] == "block"

    def test_pretooluse_info_only_uses_additional_context(self) -> None:
        """PreToolUse with INFO-only violations should use additionalContext, not systemMessage."""
        violations = [_make_violation(severity=Severity.INFO, rule_id="INFO01")]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output(event="PreToolUse")
        parsed = json.loads(output)
        assert "hookSpecificOutput" in parsed
        assert "INFO01" in parsed["hookSpecificOutput"]["additionalContext"]
        assert "systemMessage" not in parsed
        assert "permissionDecision" not in parsed.get("hookSpecificOutput", {})

    def test_no_event_uses_system_message(self) -> None:
        """Default (no event) should use systemMessage."""
        violations = [_make_violation(severity=Severity.ERROR)]
        reporter = Reporter(violations=violations)

        output = reporter.format_hook_output()
        parsed = json.loads(output)
        assert "systemMessage" in parsed


class TestBlockingViolations:
    def test_error_violations_set_blocking(self) -> None:
        violations = [_make_violation(severity=Severity.ERROR)]
        reporter = Reporter(violations=violations)
        assert reporter.has_blocking_violations() is True

    def test_warning_violations_not_blocking(self) -> None:
        violations = [_make_violation(severity=Severity.WARNING)]
        reporter = Reporter(violations=violations)
        assert reporter.has_blocking_violations() is False


class TestExitCode:
    def test_pretooluse_blocking_returns_0(self) -> None:
        """PreToolUse blocking uses exit 0 (deny protocol requires it)."""
        violations = [_make_violation(severity=Severity.ERROR)]
        reporter = Reporter(violations=violations)
        assert reporter.exit_code(event="PreToolUse") == 0

    def test_other_event_blocking_returns_2(self) -> None:
        """Non-PreToolUse blocking uses exit 2."""
        violations = [_make_violation(severity=Severity.ERROR)]
        reporter = Reporter(violations=violations)
        assert reporter.exit_code(event="PostToolUse") == 2

    def test_no_event_blocking_returns_2(self) -> None:
        """Default (no event) blocking uses exit 2."""
        violations = [_make_violation(severity=Severity.ERROR)]
        reporter = Reporter(violations=violations)
        assert reporter.exit_code() == 2

    def test_exit_code_for_non_blocking_returns_0(self) -> None:
        violations = [_make_violation(severity=Severity.WARNING)]
        reporter = Reporter(violations=violations)
        assert reporter.exit_code() == 0


class TestFormatSessionReport:
    def test_format_session_report_contains_counts(self) -> None:
        violations = [
            _make_violation(rule_id="ERR01", severity=Severity.ERROR, message="Blocked something"),
            _make_violation(rule_id="WARN01", severity=Severity.WARNING, message="Warning about something"),
        ]
        reporter = Reporter(violations=violations, rules_evaluated=5)

        report = reporter.format_session_report(files_changed=3)

        assert "Files changed: 3" in report
        assert "Rules evaluated: 5" in report
        assert "Blocked: 1" in report
        assert "Warnings: 1" in report
        assert "ERR01" in report
        assert "WARN01" in report


class TestFormatSubagentStartOutput:
    """v0.8.0 — SubagentStart additionalContext output."""

    def test_no_violations_returns_none(self) -> None:
        reporter = Reporter(violations=[])
        assert reporter.format_subagent_start_output() is None

    def test_single_violation_returns_additional_context(self) -> None:
        violations = [_make_violation(
            rule_id="subagent-safety-briefing",
            severity=Severity.INFO,
            message="SAFETY NOTICE: This subagent is unmonitored",
        )]
        reporter = Reporter(violations=violations)
        output = reporter.format_subagent_start_output()
        assert output is not None

        parsed = json.loads(output)
        assert "hookSpecificOutput" in parsed
        hook_output = parsed["hookSpecificOutput"]
        assert hook_output["hookEventName"] == "SubagentStart"
        assert "SAFETY NOTICE" in hook_output["additionalContext"]

    def test_multiple_violations_joined(self) -> None:
        violations = [
            _make_violation(message="Line one"),
            _make_violation(message="Line two"),
        ]
        reporter = Reporter(violations=violations)
        output = reporter.format_subagent_start_output()
        parsed = json.loads(output)
        context = parsed["hookSpecificOutput"]["additionalContext"]
        assert "Line one" in context
        assert "Line two" in context
        assert "\n" in context


class TestSessionReportSubagentActivity:
    """v0.8.0 — Subagent Activity section in session report."""

    def test_report_includes_subagent_spawns(self) -> None:
        reporter = Reporter(violations=[], rules_evaluated=5)
        session_state = {
            "subagents_spawned": [
                {"agent_type": "general-purpose", "agent_id": "abc-123"},
            ],
        }
        report = reporter.format_session_report(
            files_changed=0, session_state=session_state,
        )
        assert "Subagent Activity" in report
        assert "1 spawned" in report

    def test_report_includes_audit_findings(self) -> None:
        reporter = Reporter(violations=[], rules_evaluated=5)
        session_state = {
            "subagents_spawned": [{"agent_type": "general-purpose", "agent_id": "abc-123"}],
            "subagent_audits": [
                {
                    "agent_type": "general-purpose",
                    "agent_id": "abc-123",
                    "commands_count": 3,
                    "findings": [("terraform destroy", "terraform destroy -auto-approve")],
                },
            ],
        }
        report = reporter.format_session_report(
            files_changed=0, session_state=session_state,
        )
        assert "Subagent Activity" in report
        assert "1 finding" in report
        assert "terraform destroy -auto-approve" in report
        assert "abc-123" in report

    def test_report_shows_no_findings_audit(self) -> None:
        reporter = Reporter(violations=[], rules_evaluated=5)
        session_state = {
            "subagents_spawned": [{"agent_type": "Explore", "agent_id": "xyz-456"}],
            "subagent_audits": [
                {
                    "agent_type": "Explore",
                    "agent_id": "xyz-456",
                    "commands_count": 5,
                    "findings": [],
                },
            ],
        }
        report = reporter.format_session_report(
            files_changed=0, session_state=session_state,
        )
        assert "no findings" in report
        assert "xyz-456" in report

    def test_no_subagent_section_when_empty(self) -> None:
        reporter = Reporter(violations=[], rules_evaluated=5)
        report = reporter.format_session_report(files_changed=0, session_state={})
        assert "Subagent Activity" not in report

    def test_no_subagent_section_when_none(self) -> None:
        reporter = Reporter(violations=[], rules_evaluated=5)
        report = reporter.format_session_report(files_changed=0, session_state=None)
        assert "Subagent Activity" not in report

    def test_mismatched_spawns_vs_audits(self) -> None:
        """3 spawned, 1 audited — report should reflect partial audit coverage."""
        reporter = Reporter(violations=[], rules_evaluated=5)
        session_state = {
            "subagents_spawned": [
                {"agent_type": "general-purpose", "agent_id": "aaa"},
                {"agent_type": "Explore", "agent_id": "bbb"},
                {"agent_type": "general-purpose", "agent_id": "ccc"},
            ],
            "subagent_audits": [
                {
                    "agent_type": "general-purpose",
                    "agent_id": "aaa",
                    "commands_count": 2,
                    "findings": [],
                },
            ],
        }
        report = reporter.format_session_report(
            files_changed=0, session_state=session_state,
        )
        assert "3 spawned, 1 audited" in report

    def test_duplicate_agent_type_disambiguated_by_id(self) -> None:
        """Two agents of the same type should show different agent_ids."""
        reporter = Reporter(violations=[], rules_evaluated=5)
        session_state = {
            "subagents_spawned": [
                {"agent_type": "general-purpose", "agent_id": "aaa-111"},
                {"agent_type": "general-purpose", "agent_id": "bbb-222"},
            ],
            "subagent_audits": [
                {
                    "agent_type": "general-purpose",
                    "agent_id": "aaa-111",
                    "commands_count": 3,
                    "findings": [],
                },
                {
                    "agent_type": "general-purpose",
                    "agent_id": "bbb-222",
                    "commands_count": 1,
                    "findings": [("rm -rf", "rm -rf /tmp/data")],
                },
            ],
        }
        report = reporter.format_session_report(
            files_changed=0, session_state=session_state,
        )
        assert "aaa-111" in report
        assert "bbb-222" in report
        assert report.count("[general-purpose") == 2

    def test_audit_with_unknown_agent_id_no_suffix(self) -> None:
        """Agent with 'unknown' agent_id should not show id suffix."""
        reporter = Reporter(violations=[], rules_evaluated=5)
        session_state = {
            "subagents_spawned": [],
            "subagent_audits": [
                {
                    "agent_type": "Explore",
                    "agent_id": "unknown",
                    "commands_count": 2,
                    "findings": [],
                },
            ],
        }
        report = reporter.format_session_report(
            files_changed=0, session_state=session_state,
        )
        assert "[Explore]" in report
        assert "unknown" not in report.split("Subagent Activity")[1].split("[Explore]")[1]


class TestSessionReportCircuitBreaker:
    def test_report_includes_cb_activity(self) -> None:
        """Session report should show degraded rules."""
        violations = [_make_violation(severity=Severity.WARNING)]
        reporter = Reporter(violations=violations, rules_evaluated=5)
        cb_state = {
            "no-destructive-commands": {
                "fire_count": 4,
                "state": "degraded",
            },
        }
        report = reporter.format_session_report(files_changed=1, cb_state=cb_state)
        assert "Circuit Breaker" in report
        assert "no-destructive-commands" in report
        assert "degraded" in report

    def test_report_no_cb_section_when_empty(self) -> None:
        reporter = Reporter(violations=[], rules_evaluated=5)
        report = reporter.format_session_report(files_changed=0, cb_state={})
        assert "Circuit Breaker" not in report

    def test_report_no_cb_section_when_all_active(self) -> None:
        reporter = Reporter(violations=[], rules_evaluated=5)
        cb_state = {"some-rule": {"fire_count": 1, "state": "active"}}
        report = reporter.format_session_report(files_changed=0, cb_state=cb_state)
        assert "Circuit Breaker" not in report

    def test_report_no_cb_section_when_none(self) -> None:
        reporter = Reporter(violations=[], rules_evaluated=5)
        report = reporter.format_session_report(files_changed=0, cb_state=None)
        assert "Circuit Breaker" not in report
