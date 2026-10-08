"""Tests for universal token-budget rule."""

from __future__ import annotations

import time

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
        state: dict = {
            "token_budget": {
                "tool_invocations": {"Write": 159},
                "total_calls": 159,
                "total_content_bytes": 0,
                "session_start_time": time.time(),
            }
        }
        ctx = _ctx(session_state=state)
        violations = self.rule.evaluate(ctx)
        # 160 = 80% of default 200
        assert len(violations) == 1
        assert "80%" in violations[0].message

    def test_no_warn_below_threshold(self):
        state: dict = {
            "token_budget": {
                "tool_invocations": {"Write": 5},
                "total_calls": 5,
                "total_content_bytes": 0,
                "session_start_time": time.time(),
            }
        }
        ctx = _ctx(session_state=state)
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_custom_threshold(self):
        state: dict = {
            "token_budget": {
                "tool_invocations": {"Write": 79},
                "total_calls": 79,
                "total_content_bytes": 0,
                "session_start_time": time.time(),
            }
        }
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
        state: dict = {
            "token_budget": {
                "tool_invocations": {"Write": 50, "Edit": 30, "Bash": 20},
                "total_calls": 100,
                "total_content_bytes": 50000,
                "session_start_time": time.time() - 120,  # 2 minutes ago
            }
        }
        ctx = _ctx(event=HookEvent.STOP, session_state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "100 tool calls" in violations[0].message
        assert "50,000 bytes" in violations[0].message
        assert "Write: 50" in violations[0].message

    def test_report_severity_info_under_budget(self):
        state: dict = {
            "token_budget": {
                "tool_invocations": {"Write": 10},
                "total_calls": 10,
                "total_content_bytes": 1000,
                "session_start_time": time.time(),
            }
        }
        ctx = _ctx(event=HookEvent.STOP, session_state=state)
        violations = self.rule.evaluate(ctx)
        assert violations[0].severity == Severity.INFO

    def test_report_severity_warning_over_budget(self):
        state: dict = {
            "token_budget": {
                "tool_invocations": {"Write": 250},
                "total_calls": 250,
                "total_content_bytes": 100000,
                "session_start_time": time.time(),
            }
        }
        ctx = _ctx(event=HookEvent.STOP, session_state=state)
        violations = self.rule.evaluate(ctx)
        assert violations[0].severity == Severity.WARNING

    def test_empty_session_no_report(self):
        ctx = _ctx(event=HookEvent.STOP)
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_report_includes_duration(self):
        state: dict = {
            "token_budget": {
                "tool_invocations": {"Write": 5},
                "total_calls": 5,
                "total_content_bytes": 500,
                "session_start_time": time.time() - 65,  # 1m5s ago
            }
        }
        ctx = _ctx(event=HookEvent.STOP, session_state=state)
        violations = self.rule.evaluate(ctx)
        assert "1m" in violations[0].message


class TestTokenBudgetCountedTools:
    """Shell/read calls are reported but do not push a session toward 'wrap up'."""

    rule = TokenBudget()

    def _run(self, tools, config=None):
        state: dict = {}
        fired = []
        for tool in tools:
            fired += self.rule.evaluate(_ctx(tool_name=tool, session_state=state, config=config))
        return state, fired

    def test_bash_calls_do_not_trigger_mid_session_warning(self):
        state, fired = self._run(["Bash"] * 300)
        assert fired == []
        assert state["token_budget"]["total_calls"] == 300
        [report] = self.rule.evaluate(_ctx(event=HookEvent.STOP, session_state=state))
        assert report.severity == Severity.INFO
        assert "300 tool calls" in report.message and "Bash: 300" in report.message

    def test_file_changes_still_warn_with_bash_interleaved(self):
        _, fired = self._run(["Bash", "Edit"] * 160)
        assert len(fired) == 1
        assert "160/200 file-changing tool calls" in fired[0].message

    def test_count_tools_all_restores_counting_every_call(self):
        config = {"token-budget": {"count_tools": "all"}}
        _, fired = self._run(["Bash"] * 160, config)
        assert len(fired) == 1 and "160/200 tool calls" in fired[0].message

    def test_count_tools_custom_list(self):
        config = {"token-budget": {"count_tools": ["Bash"], "max_tool_invocations": 10}}
        _, fired = self._run(["Edit"] * 20 + ["Bash"] * 8, config)
        assert len(fired) == 1 and "8/10" in fired[0].message

    def test_stop_warns_only_when_counted_calls_exceed_budget(self):
        config = {"token-budget": {"max_tool_invocations": 5}}
        state, _ = self._run(["Bash"] * 50 + ["Write"] * 6, config)
        [report] = self.rule.evaluate(
            _ctx(event=HookEvent.STOP, session_state=state, config=config)
        )
        assert report.severity == Severity.WARNING
