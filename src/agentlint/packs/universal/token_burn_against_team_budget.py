"""Rule: warn when this session's token usage pushes the team over budget.

Hybrid rule — second of the new architectural class introduced in Phase 17
of the strategy plan. Pure-OSS counterpart is ``token-budget`` (per-session
tracking, already shipping). This rule layers cloud-aggregated team-wide
spend on top: even if your individual session is fine, if the team has
already burned through 90% of the monthly budget, you should know.

Self-degrading: returns silently when AgentChute is not configured.
The OSS user gets ``token-budget`` per-session warnings either way; only
licensed teams get the team-wide aggregation.

Why this is a hybrid rule instead of pure-OSS:
    The team's rolling spend window is by definition cross-machine state.
    Joe's laptop has no way to know what Sue's laptop's tokens already
    cost the team. Aggregation requires the server.

Why this is a hybrid rule instead of pure-cloud:
    The decision to *warn* the developer needs to fire on PostToolUse —
    a hot-path event. A network round-trip per tool call is unacceptable.
    A 1-hour-cached budget status from the cloud feed gives us the right
    balance: warn within ~1h of the team going over budget, no per-event
    network latency.

Cloud feed schema (``team-budget-status``):

::

    {
      "status": "ok" | "warning" | "over",
      "monthly_spend_usd": 487.23,
      "monthly_budget_usd": 500.00,
      "percent_used": 97.4,
      "days_remaining_in_period": 4,
      "as_of": "2026-05-03T12:00:00Z"
    }

The feed updates hourly server-side. With the cloud_feed 24h default TTL,
each developer's machine sees fresh budget status within at most 25h of
the team going over. Stale-fallback ensures the warning fires from
cached data even when the network is briefly down.
"""

from __future__ import annotations

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation


# Severity escalation thresholds. ``status`` from the feed takes precedence;
# these are local fallback heuristics if the feed only sends percent_used.
_PERCENT_WARN = 80.0
_PERCENT_BLOCK = 100.0


class TokenBurnAgainstTeamBudget(Rule):
    """Warn (or block) tool invocations when the team is at/over budget.

    Cloud-augmented: requires ``AGENTCHUTE_LICENSE_KEY`` to be set
    for the budget feed to be consulted. Without it, this rule is a
    silent no-op.
    """

    id = "token-burn-against-team-budget"
    description = (
        "Warns or blocks token-heavy AI operations when the team's "
        "cloud-aggregated monthly spend has hit warning or budget-cap "
        "thresholds. Self-degrades to no-op when AgentChute is not configured."
    )
    severity = Severity.WARNING
    # Fire on PostToolUse so we have just-completed-tool context, and on
    # Stop for end-of-session summary. NOT PreToolUse — we don't want to
    # block agent productivity on stale budget data.
    events = [HookEvent.POST_TOOL_USE, HookEvent.STOP]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        # context is accepted for the standard Rule signature; this rule's
        # decision is purely a function of the cloud-aggregated team budget,
        # not the per-event context.
        del context
        # Lazy import: avoid loading the agentchute module on cold-start for
        # OSS users who don't use AgentChute.
        try:
            from agentlint.agentchute import cloud_feed
        except ImportError:
            return []

        # Fetch budget feed. default=None means "no information" → no-op.
        budget = cloud_feed.get("team-budget-status", default=None, allow_network=False)
        if not budget or not isinstance(budget, dict):
            return []

        status = (budget.get("status") or "").lower()
        percent_used = self._coerce_percent(budget.get("percent_used"))

        # Decision: prefer explicit ``status`` field (authoritative) over
        # locally-derived percent thresholds. When status is set to ANY
        # known value, it overrides the percent fallback entirely — the
        # cloud may apply business logic (grace period, custom caps, etc.)
        # that the client doesn't see.
        if status in ("ok", "warning", "over"):
            if status == "over":
                return [self._build_violation(budget, severity=Severity.ERROR, over=True)]
            if status == "warning":
                return [self._build_violation(budget, severity=Severity.WARNING, over=False)]
            return []  # status == "ok"

        # Status not provided — fall back to percent thresholds.
        if percent_used is not None and percent_used >= _PERCENT_BLOCK:
            return [self._build_violation(budget, severity=Severity.ERROR, over=True)]
        if percent_used is not None and percent_used >= _PERCENT_WARN:
            return [self._build_violation(budget, severity=Severity.WARNING, over=False)]

        return []

    @staticmethod
    def _coerce_percent(raw) -> float | None:
        """Parse percent_used regardless of int/float/string shape."""
        if raw is None:
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _build_violation(
        self, budget: dict, *, severity: Severity, over: bool
    ) -> Violation:
        spend = budget.get("monthly_spend_usd")
        cap = budget.get("monthly_budget_usd")
        pct = budget.get("percent_used")
        days_left = budget.get("days_remaining_in_period")

        # Build a numeric breadcrumb only from fields the feed actually
        # provided — avoids "the team has burned $None of $None" copy.
        bits = []
        if spend is not None and cap is not None:
            bits.append(f"${spend:.0f} of ${cap:.0f}")
        if pct is not None:
            try:
                bits.append(f"{float(pct):.1f}% used")
            except (TypeError, ValueError):
                pass
        if days_left is not None:
            bits.append(f"{days_left} days left in period")
        breadcrumb = " · ".join(bits) if bits else "team budget data unavailable"

        if over:
            message = (
                f"Team has exceeded its monthly AI-spend budget "
                f"({breadcrumb}). Continued usage will be billed as overage."
            )
            suggestion = (
                "Pause non-critical agent work, switch to manual coding, "
                "or contact your engineering lead. Budget refreshes at the "
                "start of next billing cycle. Configure budget at "
                "app.agentchute.com/dashboard/billing."
            )
        else:
            message = (
                f"Team is approaching its monthly AI-spend budget "
                f"({breadcrumb})."
            )
            suggestion = (
                "Consider deferring non-critical agent tasks. View detailed "
                "spend at app.agentchute.com/dashboard."
            )

        return Violation(
            rule_id=self.id,
            message=message,
            severity=severity,
            suggestion=suggestion,
        )
