"""Base class for output formatters."""
from __future__ import annotations

from abc import ABC, abstractmethod

from agentlint.models import AgentEvent, Severity, Violation


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

    def _format_violation_lines(
        self,
        violations: list[Violation],
    ) -> list[str]:
        """Format a list of violations as human-readable lines.

        Each violation becomes one line ``[rule_id] message``,
        followed by an optional suggestion line ``  -> suggestion``.
        """
        lines: list[str] = []
        for v in violations:
            lines.append(f"[{v.rule_id}] {v.message}")
            if v.suggestion:
                lines.append(f"  -> {v.suggestion}")
        return lines
