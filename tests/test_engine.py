"""Tests for AgentLint evaluation engine."""
from __future__ import annotations

import pytest

from agentlint.config import AgentLintConfig
from agentlint.engine import Engine, EvaluationResult
from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation


# ---------------------------------------------------------------------------
# Test helper rules
# ---------------------------------------------------------------------------

class PassRule(Rule):
    id = "pass-rule"
    description = "Always passes"
    severity = Severity.INFO
    events = [HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE]
    pack = "test"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        return []


class FailRule(Rule):
    id = "fail-rule"
    description = "Always fails"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "test"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        return [Violation(rule_id=self.id, message="Failed", severity=self.severity)]


class WarnRule(Rule):
    id = "warn-rule"
    description = "Always warns"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE]
    pack = "test"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        return [Violation(rule_id=self.id, message="Warning", severity=self.severity)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def pre_tool_context() -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": "test.py"},
        project_dir="/tmp/project",
    )


@pytest.fixture
def post_tool_context() -> RuleContext:
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": "test.py"},
        project_dir="/tmp/project",
    )


@pytest.fixture
def test_config() -> AgentLintConfig:
    return AgentLintConfig(packs=["test"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEvaluationResult:
    def test_result_has_blocking_flag_for_errors(self) -> None:
        result = EvaluationResult(
            violations=[Violation(rule_id="x", message="err", severity=Severity.ERROR)]
        )
        assert result.is_blocking is True

    def test_result_not_blocking_for_warnings(self) -> None:
        result = EvaluationResult(
            violations=[Violation(rule_id="x", message="warn", severity=Severity.WARNING)]
        )
        assert result.is_blocking is False

    def test_empty_result_not_blocking(self) -> None:
        result = EvaluationResult()
        assert result.is_blocking is False


class TestEngine:
    def test_evaluate_with_no_rules(
        self, pre_tool_context: RuleContext, test_config: AgentLintConfig
    ) -> None:
        engine = Engine(config=test_config, rules=[])
        result = engine.evaluate(pre_tool_context)

        assert result.violations == []
        assert result.rules_evaluated == 0
        assert result.is_blocking is False

    def test_evaluate_matching_event_returns_violations(
        self, pre_tool_context: RuleContext, test_config: AgentLintConfig
    ) -> None:
        engine = Engine(config=test_config, rules=[FailRule()])
        result = engine.evaluate(pre_tool_context)

        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "fail-rule"
        assert result.violations[0].message == "Failed"
        assert result.rules_evaluated == 1

    def test_skips_non_matching_event(
        self, post_tool_context: RuleContext, test_config: AgentLintConfig
    ) -> None:
        """FailRule only matches PRE_TOOL_USE, so POST_TOOL_USE should skip it."""
        engine = Engine(config=test_config, rules=[FailRule()])
        result = engine.evaluate(post_tool_context)

        assert result.violations == []
        assert result.rules_evaluated == 0

    def test_skips_disabled_rules(
        self, pre_tool_context: RuleContext
    ) -> None:
        config = AgentLintConfig(
            packs=["test"],
            rules={"fail-rule": {"enabled": False}},
        )
        engine = Engine(config=config, rules=[FailRule()])
        result = engine.evaluate(pre_tool_context)

        assert result.violations == []
        assert result.rules_evaluated == 0

    def test_skips_rules_from_inactive_packs(
        self, pre_tool_context: RuleContext
    ) -> None:
        config = AgentLintConfig(packs=["universal"])  # "test" pack not active
        engine = Engine(config=config, rules=[FailRule()])
        result = engine.evaluate(pre_tool_context)

        assert result.violations == []
        assert result.rules_evaluated == 0

    def test_multiple_rules(
        self, pre_tool_context: RuleContext, test_config: AgentLintConfig
    ) -> None:
        """PassRule + FailRule both match PRE_TOOL_USE; WarnRule only POST_TOOL_USE."""
        engine = Engine(
            config=test_config,
            rules=[PassRule(), FailRule(), WarnRule()],
        )
        result = engine.evaluate(pre_tool_context)

        assert result.rules_evaluated == 2  # PassRule + FailRule
        assert len(result.violations) == 1  # only FailRule produces a violation

    def test_severity_override_strict(
        self, post_tool_context: RuleContext
    ) -> None:
        config = AgentLintConfig(severity="strict", packs=["test"])
        engine = Engine(config=config, rules=[WarnRule()])
        result = engine.evaluate(post_tool_context)

        assert len(result.violations) == 1
        # strict mode promotes WARNING -> ERROR
        assert result.violations[0].severity == Severity.ERROR
        assert result.is_blocking is True

    def test_rule_exception_does_not_crash_engine(
        self, pre_tool_context: RuleContext, test_config: AgentLintConfig
    ) -> None:
        """If a rule raises, the engine should skip it and continue."""

        class CrashingRule(Rule):
            id = "crash-rule"
            description = "Always crashes"
            severity = Severity.ERROR
            events = [HookEvent.PRE_TOOL_USE]
            pack = "test"

            def evaluate(self, context: RuleContext) -> list[Violation]:
                raise RuntimeError("Rule exploded!")

        engine = Engine(
            config=test_config,
            rules=[CrashingRule(), PassRule()],
        )
        result = engine.evaluate(pre_tool_context)

        # CrashingRule should be skipped, PassRule should still run
        assert result.rules_evaluated == 2
        assert result.violations == []  # CrashingRule's exception caught, PassRule passes


class TestEngineSuppression:
    def test_suppressed_rule_skipped(self) -> None:
        config = AgentLintConfig(packs=["test"])
        session_state: dict = {"suppressed_rules": ["warn-rule"]}
        context = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "test.py"},
            project_dir="/tmp",
            session_state=session_state,
        )
        engine = Engine(config=config, rules=[WarnRule()])
        result = engine.evaluate(context)
        assert len(result.violations) == 0

    def test_error_never_suppressed(self) -> None:
        config = AgentLintConfig(packs=["test"])
        session_state: dict = {"suppressed_rules": ["fail-rule"]}
        context = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "rm -rf /"},
            project_dir="/tmp",
            session_state=session_state,
        )
        engine = Engine(config=config, rules=[FailRule()])
        result = engine.evaluate(context)
        assert len(result.violations) == 1
        assert result.violations[0].severity == Severity.ERROR

    def test_auto_suppress_after_threshold(self) -> None:
        config = AgentLintConfig(packs=["test"])
        session_state: dict = {}
        context = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "test.py"},
            project_dir="/tmp",
            config={"auto_suppress_after": 2},
            session_state=session_state,
        )
        engine = Engine(config=config, rules=[WarnRule()])
        # Fire 1 — under threshold
        r1 = engine.evaluate(context)
        assert len(r1.violations) == 1
        # Fire 2 — at threshold
        r2 = engine.evaluate(context)
        assert len(r2.violations) == 1
        # Fire 3 — over threshold, auto-suppressed
        r3 = engine.evaluate(context)
        assert len(r3.violations) == 0
        assert "warn-rule" in session_state["suppressed_rules"]

    def test_auto_suppress_never_error(self) -> None:
        config = AgentLintConfig(packs=["test"])
        session_state: dict = {}
        context = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "rm -rf /"},
            project_dir="/tmp",
            config={"auto_suppress_after": 1},
            session_state=session_state,
        )
        engine = Engine(config=config, rules=[FailRule()])
        engine.evaluate(context)
        engine.evaluate(context)
        result = engine.evaluate(context)
        # ERRORs never auto-suppress
        assert len(result.violations) == 1
        assert "fail-rule" not in session_state.get("suppressed_rules", [])

    def test_auto_suppress_resets_on_clean(self) -> None:
        config = AgentLintConfig(packs=["test"])
        session_state: dict = {}

        # Fire warn-rule twice
        warn_ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "test.py"},
            project_dir="/tmp",
            config={"auto_suppress_after": 3},
            session_state=session_state,
        )
        engine = Engine(config=config, rules=[WarnRule()])
        engine.evaluate(warn_ctx)
        engine.evaluate(warn_ctx)
        assert session_state["rule_fire_counts"]["warn-rule"] == 2

        # Evaluate with no violations — counter should reset
        pass_ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "test.py"},
            project_dir="/tmp",
            config={"auto_suppress_after": 3},
            session_state=session_state,
        )
        engine2 = Engine(config=config, rules=[PassRule()])
        engine2.evaluate(pass_ctx)
        assert session_state["rule_fire_counts"]["warn-rule"] == 0

    def test_auto_suppress_per_rule_override(self) -> None:
        config = AgentLintConfig(packs=["test"])
        session_state: dict = {}
        context = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "test.py"},
            project_dir="/tmp",
            config={"auto_suppress_after": 10, "warn-rule": {"auto_suppress_after": 1}},
            session_state=session_state,
        )
        engine = Engine(config=config, rules=[WarnRule()])
        engine.evaluate(context)
        r2 = engine.evaluate(context)
        assert len(r2.violations) == 0
        assert "warn-rule" in session_state["suppressed_rules"]


class TestEngineCircuitBreaker:
    def test_engine_applies_circuit_breaker(self) -> None:
        """After threshold fires, engine should degrade ERROR to WARNING."""
        config = AgentLintConfig(packs=["test"])
        session_state: dict = {}
        context = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "rm -rf /"},
            project_dir="/tmp",
            session_state=session_state,
        )

        engine = Engine(config=config, rules=[FailRule()])

        # Fire 3 times — 3rd should be degraded
        for i in range(3):
            result = engine.evaluate(context)
            if i < 2:
                assert result.violations[0].severity == Severity.ERROR
            else:
                assert result.violations[0].severity == Severity.WARNING
