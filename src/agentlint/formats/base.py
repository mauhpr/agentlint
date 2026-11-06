"""Base class for output formatters."""

from __future__ import annotations

from abc import ABC, abstractmethod

from agentlint.models import AgentEvent, Violation


class OutputFormatter(ABC):
    """Abstract base for platform-specific violation formatters.

    Each adapter provides a formatter that knows how to communicate
    violations back to its agent platform (hook protocol, JSON, text, etc.).
    """

    @abstractmethod
    def format(
        self,
        violations: list[Violation],
        event: AgentEvent | str = "",
    ) -> str | None:
        """Format violations for the given event. Returns None if no violations."""

    @abstractmethod
    def exit_code(self, violations: list[Violation], event: AgentEvent | str = "") -> int:
        """Return the process exit code for this violation set and event."""

    def format_subagent_start(
        self,
        violations: list[Violation],
    ) -> str | None:
        """Format SubagentStart output for injection into subagent context.

        Default implementation delegates to format() with SUB_AGENT_START.
        Override if the platform uses a different shape for subagent context.
        """
        from agentlint.models import AgentEvent

        return self.format(violations, AgentEvent.SUB_AGENT_START)

    def add_activity_context(
        self, output: str | None, event: AgentEvent, message: str
    ) -> str | None:
        """Merge advisory context without replacing any existing policy decision."""
        import json

        from agentlint.models import Severity

        advisory = self.format([Violation("host-activity", message, Severity.INFO)], event)
        if not advisory:
            return output
        extra = json.loads(advisory)
        payload = json.loads(output) if output else {}
        for key in ("systemMessage", "additional_context", "additionalContext"):
            if extra.get(key):
                payload[key] = "\n".join(filter(None, [payload.get(key), extra[key]]))
        if extra.get("hookSpecificOutput"):
            specific = payload.setdefault("hookSpecificOutput", {})
            specific.setdefault("hookEventName", extra["hookSpecificOutput"].get("hookEventName"))
            specific["additionalContext"] = "\n".join(
                filter(
                    None,
                    [
                        specific.get("additionalContext"),
                        extra["hookSpecificOutput"].get("additionalContext"),
                    ],
                )
            )
        if "violations" in extra:
            payload.setdefault("blocked", False)
            payload.setdefault("violations", []).extend(extra["violations"])
        return json.dumps(payload)

    @staticmethod
    def _location(v: Violation) -> str | None:
        if not v.file_path:
            return None
        return f"{v.file_path}:{v.line}" if v.line else v.file_path

    def _detail_lines(self, v: Violation, indent: str = "  ") -> list[str]:
        """Location, operation, policy source and correction lines for one violation."""
        lines: list[str] = []
        location = self._location(v)
        if location:
            lines.append(f"{indent}File: {location}")
        if v.operation:
            lines.append(f"{indent}Operation: {v.operation}")
        if v.policy_source:
            lines.append(f"{indent}Policy: {v.policy_source}")
        if v.suggestion:
            lines.append(f"{indent}-> {v.suggestion}")
        return lines

    def _format_violation_lines(
        self,
        violations: list[Violation],
    ) -> list[str]:
        """Format a list of violations as human-readable lines.

        Each violation becomes one line ``[rule_id] message``, followed by
        optional ``File:``, ``Operation:``, ``Policy:`` and ``-> suggestion`` lines.
        """
        lines: list[str] = []
        for v in violations:
            lines.append(f"[{v.rule_id}] {v.message}")
            lines.extend(self._detail_lines(v))
        return lines
