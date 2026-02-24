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

    def exit_code(self, event: str = "") -> int:
        """Return exit code for Claude Code hook protocol.

        PreToolUse blocking uses exit 0 + JSON deny protocol (exit 2 ignores JSON).
        Other events use exit 2 for blocking (stderr-based).
        """
        if not self.has_blocking_violations():
            return 0
        if event == "PreToolUse":
            return 0  # Deny protocol requires exit 0 with JSON
        return 2

    def format_hook_output(self, event: str = "") -> str | None:
        """Format violations as Claude Code hook JSON output. Returns None if no violations.

        For PreToolUse ERROR violations, uses hookSpecificOutput with
        permissionDecision="deny" so Claude Code actually blocks the tool call.
        For advisory output (warnings/info), uses systemMessage.
        """
        if not self.violations:
            return None

        errors = [v for v in self.violations if v.severity == Severity.ERROR]
        warnings = [v for v in self.violations if v.severity == Severity.WARNING]
        infos = [v for v in self.violations if v.severity == Severity.INFO]

        # For PreToolUse with blocking violations, use the deny protocol
        if event == "PreToolUse" and errors:
            reason_lines = []
            for v in errors:
                reason_lines.append(f"[{v.rule_id}] {v.message}")
                if v.suggestion:
                    reason_lines.append(f"  -> {v.suggestion}")
            # Include warnings/info as additional context
            for v in warnings + infos:
                reason_lines.append(f"[{v.rule_id}] {v.message}")
                if v.suggestion:
                    reason_lines.append(f"  -> {v.suggestion}")

            return json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "\n".join(reason_lines),
                }
            })

        # Advisory output for warnings/info (or non-PreToolUse events)
        lines = ["", "AgentLint:"]

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

    def format_session_report(self, files_changed: int = 0, cb_state: dict | None = None) -> str:
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

        # Circuit breaker activity (only show non-active rules)
        if cb_state:
            degraded = {
                rid: data for rid, data in cb_state.items()
                if data.get("state", "active") != "active"
            }
            if degraded:
                lines.append("")
                lines.append("Circuit Breaker:")
                for rid, data in sorted(degraded.items()):
                    state = data.get("state", "unknown")
                    count = data.get("fire_count", 0)
                    lines.append(f"  [{rid}] {state} (fired {count}x)")

        return "\n".join(lines)
