"""Codex hook protocol: blocking JSON is consumed only on a successful exit."""

from __future__ import annotations

import json

from agentlint.formats.claude_hooks import ClaudeHookFormatter
from agentlint.models import AgentEvent, Severity, Violation


class CodexHookFormatter(ClaudeHookFormatter):
    """Use Codex's structured JSON decision path for rule violations."""

    def exit_code(self, violations: list[Violation], event: AgentEvent | str = "") -> int:
        return 0

    def format(self, violations: list[Violation], event: AgentEvent | str = "") -> str | None:
        if not violations:
            return None
        name = event.value if isinstance(event, AgentEvent) else event
        if name in {AgentEvent.USER_PROMPT.value, "UserPromptSubmit"}:
            lines = self._format_violation_lines(violations)
            output: dict = {
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": "\n".join(lines),
                }
            }
            if any(v.severity == Severity.ERROR for v in violations):
                output.update({"decision": "block", "reason": "\n".join(lines)})
            return json.dumps(output)
        if name in {AgentEvent.SESSION_START.value, "SessionStart"}:
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": "\n".join(self._format_violation_lines(violations)),
                }
            }
            if any(v.severity == Severity.ERROR for v in violations):
                output["continue"] = False
            return json.dumps(output)
        return super().format(violations, event)
