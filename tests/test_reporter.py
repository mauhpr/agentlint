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
    def test_exit_code_for_blocking_returns_2(self) -> None:
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
