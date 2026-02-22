"""Rule: track session activity and warn on excessive tool usage."""
from __future__ import annotations

import time

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation


class TokenBudget(Rule):
    """Track session activity metrics and warn on excessive usage."""

    id = "token-budget"
    description = "Tracks session activity and warns on excessive tool invocations"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE, HookEvent.STOP]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        rule_config = context.config.get(self.id, {})
        if not rule_config.get("enabled", True):
            return []

        state = context.session_state
        budget = state.setdefault("token_budget", {})

        if context.event == HookEvent.POST_TOOL_USE:
            return self._track(context, budget, rule_config)

        if context.event == HookEvent.STOP:
            return self._report(budget, rule_config)

        return []

    def _track(self, context: RuleContext, budget: dict, config: dict) -> list[Violation]:
        """Track metrics on each PostToolUse and warn at thresholds."""
        # Initialize on first call
        if "session_start_time" not in budget:
            budget["session_start_time"] = time.time()

        # Increment tool invocation count
        invocations = budget.get("tool_invocations", {})
        tool = context.tool_name or "unknown"
        invocations[tool] = invocations.get(tool, 0) + 1
        budget["tool_invocations"] = invocations

        # Track content bytes
        content = context.tool_input.get("content", "")
        budget["total_content_bytes"] = budget.get("total_content_bytes", 0) + len(content)

        # Track total calls
        total = sum(invocations.values())
        budget["total_calls"] = total

        # Warn at threshold
        max_invocations = config.get("max_tool_invocations", 200)
        warn_pct = config.get("warn_at_percent", 80)
        threshold = int(max_invocations * warn_pct / 100)

        if total == threshold:
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Session activity: {total}/{max_invocations} tool calls ({warn_pct}% of budget)",
                    severity=self.severity,
                    suggestion="Consider wrapping up or breaking this into smaller tasks.",
                )
            ]

        return []

    def _report(self, budget: dict, config: dict) -> list[Violation]:
        """Generate session activity summary at Stop."""
        total = budget.get("total_calls", 0)
        if total == 0:
            return []

        content_bytes = budget.get("total_content_bytes", 0)
        invocations = budget.get("tool_invocations", {})
        start = budget.get("session_start_time")
        duration = ""
        if start:
            elapsed = int(time.time() - start)
            minutes, seconds = divmod(elapsed, 60)
            duration = f" over {minutes}m{seconds}s"

        top_tools = sorted(invocations.items(), key=lambda x: x[1], reverse=True)[:5]
        tool_summary = ", ".join(f"{name}: {count}" for name, count in top_tools)

        max_invocations = config.get("max_tool_invocations", 200)
        severity = Severity.WARNING if total > max_invocations else Severity.INFO

        return [
            Violation(
                rule_id=self.id,
                message=f"Session activity: {total} tool calls{duration}, {content_bytes:,} bytes written. Top: {tool_summary}",
                severity=severity,
            )
        ]
