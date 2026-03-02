"""Rule: record all tool operations to a session audit log."""
from __future__ import annotations

import time

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_TRACKED_TOOLS = {"Bash", "Write", "Edit", "MultiEdit"}


class OperationJournal(Rule):
    """Record every tool operation to session_state for audit/replay."""

    id = "operation-journal"
    description = "Records all tool operations to an audit log, emits summary at Stop"
    severity = Severity.INFO
    events = [HookEvent.POST_TOOL_USE, HookEvent.STOP]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.event == HookEvent.POST_TOOL_USE:
            return self._record(context)
        if context.event == HookEvent.STOP:
            return self._summarize(context)
        return []

    def _record(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _TRACKED_TOOLS:
            return []

        journal: list[dict] = context.session_state.setdefault("operation_journal", [])
        entry: dict = {"ts": time.time(), "tool": context.tool_name}

        if context.tool_name == "Bash":
            entry["command"] = context.tool_input.get("command", "")
        else:
            entry["file_path"] = context.tool_input.get("file_path", "")

        journal.append(entry)
        return []

    def _summarize(self, context: RuleContext) -> list[Violation]:
        journal: list[dict] = context.session_state.get("operation_journal", [])
        if not journal:
            return []

        total = len(journal)
        bash_count = sum(1 for e in journal if e["tool"] == "Bash")
        write_count = total - bash_count

        return [
            Violation(
                rule_id=self.id,
                message=(
                    f"Operation journal: {total} operations this session "
                    f"({bash_count} shell, {write_count} file writes)"
                ),
                severity=self.severity,
                suggestion="Full journal available in session_state['operation_journal'] for replay/audit.",
            )
        ]
