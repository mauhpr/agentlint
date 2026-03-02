"""Tests for autopilot pack PostToolUse and Stop rules."""
from __future__ import annotations

import time

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.operation_journal import OperationJournal


def _ctx_post(tool_name: str, tool_input: dict, state: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
        config={},
        session_state=state if state is not None else {},
    )


def _ctx_stop(state: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.STOP,
        tool_name="",
        tool_input={},
        project_dir="/tmp/project",
        config={},
        session_state=state if state is not None else {},
    )


class TestOperationJournal:
    rule = OperationJournal()

    def test_records_bash_command_to_journal(self):
        state = {}
        ctx = _ctx_post("Bash", {"command": "ls -la"}, state=state)
        self.rule.evaluate(ctx)
        assert "operation_journal" in state
        assert len(state["operation_journal"]) == 1
        entry = state["operation_journal"][0]
        assert entry["tool"] == "Bash"
        assert entry["command"] == "ls -la"
        assert "ts" in entry

    def test_records_multiple_commands(self):
        state = {}
        for cmd in ["ls", "pwd", "whoami"]:
            ctx = _ctx_post("Bash", {"command": cmd}, state=state)
            self.rule.evaluate(ctx)
        assert len(state["operation_journal"]) == 3

    def test_records_write_tool(self):
        state = {}
        ctx = _ctx_post("Write", {"file_path": "foo.py", "content": "x=1"}, state=state)
        self.rule.evaluate(ctx)
        assert len(state["operation_journal"]) == 1
        assert state["operation_journal"][0]["tool"] == "Write"

    def test_post_returns_no_violations(self):
        state = {}
        ctx = _ctx_post("Bash", {"command": "ls"}, state=state)
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_stop_emits_journal_summary(self):
        state = {
            "operation_journal": [
                {"ts": time.time(), "tool": "Bash", "command": "ls -la"},
                {"ts": time.time(), "tool": "Write", "file_path": "app.py"},
            ]
        }
        ctx = _ctx_stop(state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.INFO
        assert "2 operations" in violations[0].message

    def test_stop_with_empty_journal_no_violation(self):
        ctx = _ctx_stop(state={})
        violations = self.rule.evaluate(ctx)
        assert violations == []
