"""Gemini CLI hook protocol formatter."""
from __future__ import annotations

import json

from agentlint.formats.base import OutputFormatter
from agentlint.models import AgentEvent, Severity, Violation


class GeminiHookFormatter(OutputFormatter):
    """Formats violations for the Gemini CLI hook protocol.

    Gemini CLI uses JSON stdout with specific shapes:
    - Blocking: {"decision": "deny", "reason": "...", "systemMessage": "..."}
    - Context injection: {"hookSpecificOutput": {"hookEventName": "...", "additionalContext": "..."}}
    - Allow: {"decision": "allow"}

    Exit codes are not the primary blocking mechanism; the JSON decision field is.
    However, exit code 2 can also block for some events.
    """

    def exit_code(self, violations: list[Violation], event: AgentEvent | str = "") -> int:
        """Return exit code for Gemini hook protocol.

        Gemini primarily uses JSON stdout for decisions, but exit 2 can also block.
        We return 0 for allow and 2 for block to be safe on both mechanisms.
        """
        has_errors = any(v.severity == Severity.ERROR for v in violations)
        return 2 if has_errors else 0

    def format(
        self,
        violations: list[Violation],
        event: AgentEvent | str = "",
    ) -> str | None:
        """Format violations as Gemini hook JSON output."""
        if not violations:
            return None

        event_str = event.value if isinstance(event, AgentEvent) else event

        errors = [v for v in violations if v.severity == Severity.ERROR]
        warnings = [v for v in violations if v.severity == Severity.WARNING]
        infos = [v for v in violations if v.severity == Severity.INFO]

        # Build formatted violation lines
        context_lines = self._format_violation_lines(errors + warnings + infos)

        # For blocking events (BeforeTool, BeforeAgent, BeforeModel)
        if errors and event_str in (
            AgentEvent.PRE_TOOL_USE.value,
            "BeforeTool",
            "BeforeAgent",
            "BeforeModel",
            "BeforeToolSelection",
        ):
            reason_lines = self._format_violation_lines(errors)
            return json.dumps({
                "decision": "deny",
                "reason": "\n".join(reason_lines),
                "systemMessage": "AgentLint blocked this action.",
            })

        # For post-execution events (AfterTool, AfterAgent, AfterModel)
        if event_str in (
            AgentEvent.POST_TOOL_USE.value,
            "AfterTool",
            "AfterAgent",
            "AfterModel",
        ):
            return json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": event_str,
                    "additionalContext": "\n".join(context_lines),
                }
            })

        # For other events — use additionalContext via hookSpecificOutput
        return json.dumps({
            "hookSpecificOutput": {
                "hookEventName": event_str,
                "additionalContext": "\n".join(context_lines),
            }
        })

    def format_subagent_start(
        self,
        violations: list[Violation],
    ) -> str | None:
        """Format SubagentStart output for Gemini."""
        if not violations:
            return None

        context_lines = [v.message for v in violations]
        return json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SubagentStart",
                "additionalContext": "\n".join(context_lines),
            }
        })
