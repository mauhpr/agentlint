"""Claude Code hook protocol formatter."""
from __future__ import annotations

import json

from agentlint.formats.base import OutputFormatter
from agentlint.models import AgentEvent, Severity, Violation


class ClaudeHookFormatter(OutputFormatter):
    """Formats violations for the Claude Code hook protocol.

    Produces JSON output that Claude Code interprets as:
    - hookSpecificOutput with permissionDecision="deny" for PreToolUse blocking
    - hookSpecificOutput with additionalContext for advisory violations
    - systemMessage for user-visible events (Stop, Notification, etc.)
    """

    def exit_code(self, violations: list[Violation], event: AgentEvent | str = "") -> int:
        """Return exit code for Claude Code hook protocol.

        PreToolUse blocking uses exit 0 + JSON deny protocol (exit 2 ignores JSON).
        Other events use exit 2 for blocking (stderr-based).
        """
        has_errors = any(v.severity == Severity.ERROR for v in violations)
        if not has_errors:
            return 0
        event_str = event.value if isinstance(event, AgentEvent) else event
        if event_str == AgentEvent.PRE_TOOL_USE.value or event_str == "PreToolUse":
            return 0  # Deny protocol requires exit 0 with JSON
        return 2

    def format(
        self,
        violations: list[Violation],
        event: AgentEvent | str = "",
    ) -> str | None:
        """Format violations as Claude Code hook JSON output."""
        if not violations:
            return None

        event_str = event.value if isinstance(event, AgentEvent) else event

        errors = [v for v in violations if v.severity == Severity.ERROR]
        warnings = [v for v in violations if v.severity == Severity.WARNING]
        infos = [v for v in violations if v.severity == Severity.INFO]

        # For PreToolUse with blocking violations, use the deny protocol
        if (event_str == AgentEvent.PRE_TOOL_USE.value or event_str == "PreToolUse") and errors:
            reason_lines = self._format_violation_lines(errors)
            reason_lines.extend(self._format_violation_lines(warnings + infos))

            return json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": "\n".join(reason_lines),
                }
            })

        # Build formatted violation lines for reuse across output paths
        context_lines = self._format_violation_lines(errors + warnings + infos)

        # PreToolUse advisory (no errors) — inject into agent context before tool runs
        if event_str == AgentEvent.PRE_TOOL_USE.value or event_str == "PreToolUse":
            return json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": "\n".join(context_lines),
                }
            })

        # PostToolUse — inject into agent context so it influences next action
        if event_str in (AgentEvent.POST_TOOL_USE.value, AgentEvent.POST_TOOL_FAILURE.value, "PostToolUse", "PostToolUseFailure"):
            result: dict = {
                "hookSpecificOutput": {
                    "hookEventName": event_str,
                    "additionalContext": "\n".join(context_lines),
                }
            }
            if warnings or errors:
                reason_violations = errors + warnings
                result["decision"] = "block"
                result["reason"] = "\n".join(
                    f"[{v.rule_id}] {v.message}" for v in reason_violations
                )
            return json.dumps(result)

        # Other events (Stop, Notification, etc.) — systemMessage for user visibility
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

    def format_subagent_start(
        self,
        violations: list[Violation],
    ) -> str | None:
        """Format SubagentStart output with additionalContext for injection into subagent."""
        if not violations:
            return None

        context_lines = [v.message for v in violations]
        return json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": "\n".join(context_lines),
            }
        })
