"""Cursor IDE hook protocol formatter."""
from __future__ import annotations

import json

from agentlint.formats.base import OutputFormatter
from agentlint.models import AgentEvent, Severity, Violation


class CursorHookFormatter(OutputFormatter):
    """Formats violations for the Cursor hook protocol.

    Cursor hooks receive JSON on stdin and emit JSON on stdout.
    Exit codes:
    - 0: success, use JSON output
    - 2: block the action
    - other: hook failure, action continues

    Blocking output shape:
        {"permission": "deny", "user_message": "...", "agent_message": "..."}

    Advisory output (postToolUse) shape:
        {"additional_context": "..."}
    """

    def exit_code(self, violations: list[Violation], event: AgentEvent | str = "") -> int:
        """Return exit code for Cursor hook protocol.

        Cursor uses exit 2 to block actions. Exit 0 means proceed.
        """
        has_errors = any(v.severity == Severity.ERROR for v in violations)
        if has_errors:
            return 2
        return 0

    def format(
        self,
        violations: list[Violation],
        event: AgentEvent | str = "",
    ) -> str | None:
        """Format violations as Cursor hook JSON output."""
        if not violations:
            return None

        event_str = event.value if isinstance(event, AgentEvent) else event

        errors = [v for v in violations if v.severity == Severity.ERROR]
        warnings = [v for v in violations if v.severity == Severity.WARNING]
        infos = [v for v in violations if v.severity == Severity.INFO]

        # Build formatted violation lines
        context_lines = self._format_violation_lines(errors + warnings + infos)

        # For blocking events (preToolUse, beforeShellExecution, beforeMCPExecution, beforeReadFile)
        if errors and event_str in (
            AgentEvent.PRE_TOOL_USE.value,
            "preToolUse",
            "beforeShellExecution",
            "beforeMCPExecution",
            "beforeReadFile",
            "beforeSubmitPrompt",
        ):
            reason_lines = self._format_violation_lines(errors)
            return json.dumps({
                "permission": "deny",
                "user_message": "AgentLint blocked this action.",
                "agent_message": "\n".join(reason_lines),
            })

        # For postToolUse / afterFileEdit / afterShellExecution — inject additional_context
        if event_str in (
            AgentEvent.POST_TOOL_USE.value,
            "postToolUse",
            "afterFileEdit",
            "afterShellExecution",
            "afterMCPExecution",
        ):
            return json.dumps({
                "additional_context": "\n".join(context_lines),
            })

        # For stop / sessionEnd / other events — return as text info
        return json.dumps({
            "additional_context": "\n".join(context_lines),
        })

    def format_subagent_start(
        self,
        violations: list[Violation],
    ) -> str | None:
        """Format SubagentStart output for Cursor.

        Cursor subagentStart hooks can inject context via additional_context
        or return permission decisions.
        """
        if not violations:
            return None

        context_lines = [v.message for v in violations]
        return json.dumps({
            "additional_context": "\n".join(context_lines),
        })
