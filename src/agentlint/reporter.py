"""Output formatting for Claude Code hook protocol."""
from __future__ import annotations

import json

from agentlint.models import Severity, Violation


class Reporter:
    """Formats violations for Claude Code hook output."""

    def __init__(self, violations: list[Violation], rules_evaluated: int = 0):
        self.violations = violations
        self.rules_evaluated = rules_evaluated

    def has_blocking_violations(self) -> bool:
        return any(v.severity == Severity.ERROR for v in self.violations)

    def exit_code(self) -> int:
        return 2 if self.has_blocking_violations() else 0

    def format_hook_output(self) -> str | None:
        """Format violations as Claude Code hook JSON output. Returns None if no violations."""
        if not self.violations:
            return None

        lines = ["", "AgentLint:"]

        errors = [v for v in self.violations if v.severity == Severity.ERROR]
        warnings = [v for v in self.violations if v.severity == Severity.WARNING]
        infos = [v for v in self.violations if v.severity == Severity.INFO]

        if errors:
            lines.append("  BLOCKED:")
            for v in errors:
                lines.append(f"    [{v.rule_id}] {v.message}")
                if v.suggestion:
                    lines.append(f"      -> {v.suggestion}")

        if warnings:
            lines.append("  WARNINGS:")
            for v in warnings:
                lines.append(f"    [{v.rule_id}] {v.message}")
                if v.suggestion:
                    lines.append(f"      -> {v.suggestion}")

        if infos:
            lines.append("  INFO:")
            for v in infos:
                lines.append(f"    [{v.rule_id}] {v.message}")
                if v.suggestion:
                    lines.append(f"      -> {v.suggestion}")

        return json.dumps({"systemMessage": "\n".join(lines)})

    def format_session_report(self, files_changed: int = 0) -> str:
        """Format a session summary report for the Stop event."""
        errors = [v for v in self.violations if v.severity == Severity.ERROR]
        warnings = [v for v in self.violations if v.severity == Severity.WARNING]

        lines = [
            "AgentLint Session Report",
            f"Files changed: {files_changed}  |  Rules evaluated: {self.rules_evaluated}",
            f"Passed: {self.rules_evaluated - len(self.violations)}  |  "
            f"Warnings: {len(warnings)}  |  Blocked: {len(errors)}",
        ]

        if errors:
            lines.append("")
            lines.append("Blocked actions:")
            for v in errors:
                lines.append(f"  [{v.rule_id}] {v.message}")

        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for v in warnings:
                lines.append(f"  [{v.rule_id}] {v.message}")

        return "\n".join(lines)
