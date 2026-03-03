"""Tests for subagent-safety-briefing rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.subagent_safety_briefing import SubagentSafetyBriefing


def _ctx(
    agent_type: str | None = None,
    agent_id: str | None = None,
    session_state: dict | None = None,
) -> RuleContext:
    return RuleContext(
        event=HookEvent.SUB_AGENT_START,
        tool_name="",
        tool_input={},
        project_dir="/tmp/project",
        session_state=session_state if session_state is not None else {},
        agent_type=agent_type,
        agent_id=agent_id,
    )


class TestSubagentSafetyBriefing:
    rule = SubagentSafetyBriefing()

    def test_fires_on_subagent_start(self):
        ctx = _ctx(agent_type="general-purpose", agent_id="abc-123")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.INFO

    def test_message_contains_safety_notice(self):
        ctx = _ctx()
        violations = self.rule.evaluate(ctx)
        assert "SAFETY NOTICE" in violations[0].message
        assert "not monitored" in violations[0].message

    def test_message_mentions_destructive_ops(self):
        ctx = _ctx()
        violations = self.rule.evaluate(ctx)
        msg = violations[0].message
        assert "terraform destroy" in msg
        assert "DROP DATABASE" in msg
        assert "iptables flush" in msg

    def test_records_spawn_in_session_state(self):
        session_state: dict = {}
        ctx = _ctx(agent_type="general-purpose", agent_id="abc-123", session_state=session_state)
        self.rule.evaluate(ctx)

        assert "subagents_spawned" in session_state
        assert len(session_state["subagents_spawned"]) == 1
        assert session_state["subagents_spawned"][0]["agent_type"] == "general-purpose"
        assert session_state["subagents_spawned"][0]["agent_id"] == "abc-123"

    def test_accumulates_multiple_spawns(self):
        session_state: dict = {}
        ctx1 = _ctx(agent_type="general-purpose", agent_id="abc-123", session_state=session_state)
        ctx2 = _ctx(agent_type="Explore", agent_id="def-456", session_state=session_state)

        self.rule.evaluate(ctx1)
        self.rule.evaluate(ctx2)

        assert len(session_state["subagents_spawned"]) == 2

    def test_handles_missing_agent_type(self):
        ctx = _ctx(agent_type=None, agent_id=None)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        # Should default to "unknown"
        assert ctx.session_state["subagents_spawned"][0]["agent_type"] == "unknown"
        assert ctx.session_state["subagents_spawned"][0]["agent_id"] == "unknown"

    def test_rule_id(self):
        assert self.rule.id == "subagent-safety-briefing"

    def test_rule_pack(self):
        assert self.rule.pack == "autopilot"

    def test_rule_events(self):
        assert self.rule.events == [HookEvent.SUB_AGENT_START]

    def test_matches_subagent_start_event(self):
        assert self.rule.matches_event(HookEvent.SUB_AGENT_START)

    def test_does_not_match_other_events(self):
        assert not self.rule.matches_event(HookEvent.PRE_TOOL_USE)
        assert not self.rule.matches_event(HookEvent.SUB_AGENT_STOP)
        assert not self.rule.matches_event(HookEvent.STOP)
