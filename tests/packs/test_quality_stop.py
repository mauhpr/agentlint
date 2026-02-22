"""Tests for quality pack Stop rules."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.quality.self_review_prompt import SelfReviewPrompt


def _ctx(config: dict | None = None, session_state: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.STOP,
        tool_name="",
        tool_input={},
        project_dir="/tmp/project",
        config=config or {},
        session_state=session_state or {},
    )


class TestSelfReviewPrompt:
    rule = SelfReviewPrompt()

    def test_returns_default_prompt(self):
        violations = self.rule.evaluate(_ctx())
        assert len(violations) == 1
        assert "senior engineer" in violations[0].message
        assert "logic errors" in violations[0].message

    def test_custom_prompt(self):
        config = {"self-review-prompt": {"custom_prompt": "Check for bugs."}}
        violations = self.rule.evaluate(_ctx(config=config))
        assert len(violations) == 1
        assert violations[0].message == "Check for bugs."

    def test_disabled(self):
        config = {"self-review-prompt": {"enabled": False}}
        violations = self.rule.evaluate(_ctx(config=config))
        assert violations == []

    def test_severity_is_info(self):
        violations = self.rule.evaluate(_ctx())
        assert violations[0].severity.value == "info"
