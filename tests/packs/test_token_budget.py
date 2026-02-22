"""Tests for universal token-budget rule."""
from __future__ import annotations

import time
from unittest.mock import patch

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.universal.token_budget import TokenBudget


def _ctx(
    event: HookEvent = HookEvent.POST_TOOL_USE,
    tool_name: str = "Write",
    tool_input: dict | None = None,
    config: dict | None = None,
    session_state: dict | None = None,
) -> RuleContext:
    return RuleContext(
        event=event,
        tool_name=tool_name,
        tool_input=tool_input or {},
        project_dir="/tmp/project",
        config=config or {},
        session_state=session_state if session_state is not None else {},
    )


class TestTokenBudgetTracking:
    rule = TokenBudget()

    def test_tracks_tool_invocations(self):
        state: dict = {}
        ctx = _ctx(tool_name="Write", session_state=state)
        self.rule.evaluate(ctx)
        assert state["token_budget"]["tool_invocations"]["Write"] == 1

    def test_increments_invocations(self):
        state: dict = {}
        for _ in range(5):
            ctx = _ctx(tool_name="Edit", session_state=state)
            self.rule.evaluate(ctx)
        assert state["token_budget"]["tool_invocations"]["Edit"] == 5
        assert state["token_budget"]["total_calls"] == 5

    def test_tracks_content_bytes(self):
        state: dict = {}
        ctx = _ctx(
            tool_name="Write",
            tool_input={"content": "hello world"},
            session_state=state,
        )
        self.rule.evaluate(ctx)
        assert state["token_budget"]["total_content_bytes"] == 11

    def test_warns_at_threshold(self):
        state: dict = {"token_budget": {
            "tool_invocations": {"Write": 159},
            "total_calls": 159,
            "total_content_bytes": 0,
            "session_start_time": time.time(),
        }}
        ctx = _ctx(session_state=state)
        violations = self.rule.evaluate(ctx)
        # 160 = 80% of default 200
        assert len(violations) == 1
        assert "80%" in violations[0].message

    def test_no_warn_below_threshold(self):
        state: dict = {"token_budget": {
            "tool_invocations": {"Write": 5},
            "total_calls": 5,
            "total_content_bytes": 0,
            "session_start_time": time.time(),
        }}
        ctx = _ctx(session_state=state)
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_custom_threshold(self):
        state: dict = {"token_budget": {
            "tool_invocations": {"Write": 79},
            "total_calls": 79,
            "total_content_bytes": 0,
            "session_start_time": time.time(),
        }}
        config = {"token-budget": {"max_tool_invocations": 100, "warn_at_percent": 80}}
        ctx = _ctx(session_state=state, config=config)
        violations = self.rule.evaluate(ctx)
        # 80 = 80% of 100
        assert len(violations) == 1
        assert "80%" in violations[0].message

    def test_disabled(self):
        config = {"token-budget": {"enabled": False}}
        ctx = _ctx(config=config)
        violations = self.rule.evaluate(ctx)
        assert violations == []


class TestTokenBudgetReport:
    rule = TokenBudget()

    def test_reports_summary_at_stop(self):
        state: dict = {"token_budget": {
            "tool_invocations": {"Write": 50, "Edit": 30, "Bash": 20},
            "total_calls": 100,
            "total_content_bytes": 50000,
            "session_start_time": time.time() - 120,  # 2 minutes ago
        }}
        ctx = _ctx(event=HookEvent.STOP, session_state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "100 tool calls" in violations[0].message
        assert "50,000 bytes" in violations[0].message
        assert "Write: 50" in violations[0].message

    def test_report_severity_info_under_budget(self):
        state: dict = {"token_budget": {
            "tool_invocations": {"Write": 10},
            "total_calls": 10,
            "total_content_bytes": 1000,
            "session_start_time": time.time(),
        }}
        ctx = _ctx(event=HookEvent.STOP, session_state=state)
        violations = self.rule.evaluate(ctx)
        assert violations[0].severity == Severity.INFO

    def test_report_severity_warning_over_budget(self):
        state: dict = {"token_budget": {
            "tool_invocations": {"Write": 250},
            "total_calls": 250,
            "total_content_bytes": 100000,
            "session_start_time": time.time(),
        }}
        ctx = _ctx(event=HookEvent.STOP, session_state=state)
        violations = self.rule.evaluate(ctx)
        assert violations[0].severity == Severity.WARNING

    def test_empty_session_no_report(self):
        ctx = _ctx(event=HookEvent.STOP)
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_report_includes_duration(self):
        state: dict = {"token_budget": {
            "tool_invocations": {"Write": 5},
            "total_calls": 5,
            "total_content_bytes": 500,
            "session_start_time": time.time() - 65,  # 1m5s ago
        }}
        ctx = _ctx(event=HookEvent.STOP, session_state=state)
        violations = self.rule.evaluate(ctx)
        assert "1m" in violations[0].message
