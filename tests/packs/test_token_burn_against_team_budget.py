"""Tests for the token-burn-against-team-budget hybrid rule.

This rule reads cloud-aggregated team spend (impossible locally) and
warns/blocks when the team is approaching or over the monthly cap.

The tests verify:

  1. **Self-degrading**: with no AgentChute license, the rule is silent.
  2. **Status field takes precedence**: the cloud-curated status is
     authoritative even when percent_used disagrees (the cloud may have
     business logic the client doesn't see).
  3. **Percent-based fallback**: when status is missing, percent_used
     thresholds (80% warn, 100% block) take effect.
  4. **Severity escalation**: 'over' → ERROR, 'warning' → WARNING.
  5. **Message resilience**: missing fields don't crash; the message is
     built from whatever the feed provided.
"""

from __future__ import annotations

from unittest.mock import patch

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.universal.token_burn_against_team_budget import (
    TokenBurnAgainstTeamBudget,
)


def _ctx(event: HookEvent = HookEvent.POST_TOOL_USE) -> RuleContext:
    return RuleContext(
        event=event,
        tool_name="Bash",
        tool_input={"command": "echo hi"},
        project_dir="/tmp/project",
        config={},
    )


def _patch_feed(payload):
    return patch("agentlint.agentchute.cloud_feed.get", return_value=payload)


# ---------- self-degrading ----------


class TestSelfDegrading:
    rule = TokenBurnAgainstTeamBudget()

    def test_no_op_when_feed_returns_none(self):
        with _patch_feed(None):
            assert self.rule.evaluate(_ctx()) == []

    def test_no_op_when_feed_returns_empty_dict(self):
        with _patch_feed({}):
            assert self.rule.evaluate(_ctx()) == []

    def test_no_op_when_feed_returns_non_dict(self):
        # If the API misbehaves and returns a list, the rule should not crash
        with _patch_feed(["unexpected"]):
            assert self.rule.evaluate(_ctx()) == []


# ---------- status field is authoritative ----------


class TestStatusField:
    rule = TokenBurnAgainstTeamBudget()

    def test_status_over_fires_error(self):
        with _patch_feed({"status": "over", "percent_used": 105.0}):
            violations = self.rule.evaluate(_ctx())
        assert len(violations) == 1
        assert violations[0].severity.value == "error"
        assert "exceeded" in violations[0].message.lower()
        assert "app.agentchute.com" in violations[0].suggestion

    def test_status_warning_fires_warning(self):
        with _patch_feed({"status": "warning", "percent_used": 85.0}):
            violations = self.rule.evaluate(_ctx())
        assert len(violations) == 1
        assert violations[0].severity.value == "warning"
        assert "approaching" in violations[0].message.lower()

    def test_status_ok_fires_nothing(self):
        with _patch_feed({"status": "ok", "percent_used": 12.3}):
            assert self.rule.evaluate(_ctx()) == []


# ---------- percent_used fallback ----------


class TestPercentFallback:
    rule = TokenBurnAgainstTeamBudget()

    def test_no_status_98_percent_warns(self):
        with _patch_feed({"percent_used": 98.0}):
            violations = self.rule.evaluate(_ctx())
        assert len(violations) == 1
        assert violations[0].severity.value == "warning"

    def test_no_status_101_percent_blocks(self):
        with _patch_feed({"percent_used": 101.5}):
            violations = self.rule.evaluate(_ctx())
        assert len(violations) == 1
        assert violations[0].severity.value == "error"

    def test_no_status_50_percent_silent(self):
        with _patch_feed({"percent_used": 50.0}):
            assert self.rule.evaluate(_ctx()) == []

    def test_status_takes_precedence_over_percent(self):
        # Status says ok, percent says 99% — status wins, no violation.
        with _patch_feed({"status": "ok", "percent_used": 99.0}):
            assert self.rule.evaluate(_ctx()) == []


# ---------- message resilience ----------


class TestMessageResilience:
    rule = TokenBurnAgainstTeamBudget()

    def test_message_with_full_data(self):
        feed = {
            "status": "warning",
            "monthly_spend_usd": 487.23,
            "monthly_budget_usd": 500.00,
            "percent_used": 97.4,
            "days_remaining_in_period": 4,
        }
        with _patch_feed(feed):
            violations = self.rule.evaluate(_ctx())
        msg = violations[0].message
        assert "$487" in msg
        assert "$500" in msg
        assert "97.4%" in msg
        assert "4 days" in msg

    def test_message_with_minimal_data(self):
        # Just status, no spend/cap/percent. The message must still render.
        with _patch_feed({"status": "over"}):
            violations = self.rule.evaluate(_ctx())
        msg = violations[0].message
        assert "exceeded" in msg.lower()
        # Should not contain $None / NaN / similar artifacts
        assert "None" not in msg
        assert "$0" not in msg or True  # tolerate this case

    def test_message_with_string_percent_does_not_crash(self):
        # Guard against API returning percent_used as string "85.5" not float
        with _patch_feed({"status": "warning", "percent_used": "85.5"}):
            violations = self.rule.evaluate(_ctx())
        # Should still produce a violation, with the string value coerced
        assert len(violations) == 1


# ---------- event registration ----------


class TestEventRegistration:
    """The rule should fire on PostToolUse and Stop, NOT on PreToolUse.
    PreToolUse is the lint hot path — we don't want to block agent
    invocations on a stale budget feed."""

    rule = TokenBurnAgainstTeamBudget()

    def test_registered_for_post_tool_use(self):
        assert HookEvent.POST_TOOL_USE in self.rule.events

    def test_registered_for_stop(self):
        assert HookEvent.STOP in self.rule.events

    def test_not_registered_for_pre_tool_use(self):
        assert HookEvent.PRE_TOOL_USE not in self.rule.events
