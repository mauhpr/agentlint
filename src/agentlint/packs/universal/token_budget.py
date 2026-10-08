"""Rule: track session activity and warn on excessive tool usage."""

from __future__ import annotations

import time

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

# By default the budget counts file-changing calls only. Shell and read calls are
# still tallied for the Stop summary, but they do not move a session toward the
# "consider wrapping up" warning: long verification work (tests, git, CI checks)
# should not push an agent to stop early. Set `count_tools: all` to count every call.
_DEFAULT_COUNT_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})


def _counted_tools(config: dict) -> frozenset[str] | None:
    """Tool names that count toward the budget; None means every tool."""
    value = config.get("count_tools")
    if value == "all":
        return None
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return frozenset(value)
    return _DEFAULT_COUNT_TOOLS


def _budget_calls(budget: dict, counted: frozenset[str] | None) -> int:
    invocations = budget.get("tool_invocations", {})
    if counted is None:
        return sum(invocations.values())
    return sum(n for tool, n in invocations.items() if tool in counted)


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

        # Track total calls (all tools) and the calls that count toward the budget
        budget["total_calls"] = sum(invocations.values())
        counted = _counted_tools(config)
        if counted is not None and tool not in counted:
            return []
        total = _budget_calls(budget, counted)

        # Warn at threshold
        max_invocations = config.get("max_tool_invocations", 200)
        warn_pct = config.get("warn_at_percent", 80)
        threshold = int(max_invocations * warn_pct / 100)
        kind = "tool calls" if counted is None else "file-changing tool calls"

        if total == threshold:
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Session activity: {total}/{max_invocations} {kind} ({warn_pct}% of budget)",
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
        counted_total = _budget_calls(budget, _counted_tools(config))
        severity = Severity.WARNING if counted_total > max_invocations else Severity.INFO

        return [
            Violation(
                rule_id=self.id,
                message=f"Session activity: {total} tool calls{duration}, {content_bytes:,} bytes written. Top: {tool_summary}",
                severity=severity,
            )
        ]
