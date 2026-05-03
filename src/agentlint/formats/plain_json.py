"""Plain JSON formatter — agent-agnostic output."""
from __future__ import annotations

import json

from agentlint.formats.base import OutputFormatter
from agentlint.models import AgentEvent, Severity, Violation


class PlainJsonFormatter(OutputFormatter):
    """Formats violations as plain JSON.

    Returns a structured JSON object that any agent framework can parse:
    {
      "blocked": bool,
      "violations": [
        {"rule_id": "...", "message": "...", "severity": "...", ...}
      ]
    }
    """

    def exit_code(self, violations: list[Violation], event: AgentEvent | str = "") -> int:
        has_errors = any(v.severity == Severity.ERROR for v in violations)
        return 1 if has_errors else 0

    def format(
        self,
        violations: list[Violation],
        event: AgentEvent | str = "",
    ) -> str | None:
        if not violations:
            return None

        has_errors = any(v.severity == Severity.ERROR for v in violations)
        return json.dumps({
            "blocked": has_errors,
            "violations": [v.to_dict() for v in violations],
        })

    def format_subagent_start(
        self,
        violations: list[Violation],
    ) -> str | None:
        return self.format(violations, AgentEvent.SUB_AGENT_START)
