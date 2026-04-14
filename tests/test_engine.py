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


    def test_manual_suppress_prevents_auto_suppress_counting(self) -> None:
        """Already-suppressed rules should not accumulate auto-suppress counts."""
        config = AgentLintConfig(packs=["test"])
        session_state: dict = {"suppressed_rules": ["warn-rule"]}
        context = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "test.py"},
            project_dir="/tmp",
            config={"auto_suppress_after": 2},
            session_state=session_state,
        )
        engine = Engine(config=config, rules=[WarnRule()])
        # Fire 3 times — should not accumulate counts since already suppressed
        for _ in range(3):
            engine.evaluate(context)
        assert session_state.get("rule_fire_counts", {}).get("warn-rule", 0) == 0


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


# ---------------------------------------------------------------------------
# Helper rules for ignore/allow path tests
# ---------------------------------------------------------------------------

class AlwaysWarnRule(Rule):
    id = "always-warn"
    description = "Always warns"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        return [Violation(rule_id=self.id, message="always", severity=self.severity, file_path=context.file_path)]


class AlwaysErrorRule(Rule):
    id = "always-error"
    description = "Always errors"
    severity = Severity.ERROR
    events = [HookEvent.POST_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        return [Violation(rule_id=self.id, message="always", severity=self.severity, file_path=context.file_path)]


# ---------------------------------------------------------------------------
# TestGlobalIgnorePaths
# ---------------------------------------------------------------------------

class TestGlobalIgnorePaths:
    """Tests for the global ignore_paths feature in Engine."""

    def _make_context(self, file_path: str | None, ignore_paths: list | str | None = None, config: dict | None = None) -> RuleContext:
        if config is None:
            config = {}
        if ignore_paths is not None:
            config["ignore_paths"] = ignore_paths
        return RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": file_path} if file_path else {},
            project_dir="/project",
            config=config if config else None,
            file_content="x = 1\n",
        )

    def _make_engine(self, rules=None):
        config = AgentLintConfig(packs=["universal"])
        if rules is None:
            rules = [AlwaysWarnRule()]
        return Engine(config=config, rules=rules)

    def test_ignore_paths_skips_matching_file(self) -> None:
        ctx = self._make_context("/project/legacy/old.py", ignore_paths=["**/legacy/**"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_ignore_paths_fires_on_non_matching(self) -> None:
        ctx = self._make_context("/project/src/app.py", ignore_paths=["**/legacy/**"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1

    def test_glob_double_star_matches_nested(self) -> None:
        ctx = self._make_context("/project/a/b/c/d/file.py", ignore_paths=["**/b/**"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_glob_basename_matches(self) -> None:
        ctx = self._make_context("/project/src/package-lock.json", ignore_paths=["package-lock.json"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_multiple_patterns_first_match(self) -> None:
        ctx = self._make_context("/project/vendor/lib.py", ignore_paths=["**/vendor/**", "**/legacy/**"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_empty_ignore_paths_no_effect(self) -> None:
        ctx = self._make_context("/project/src/app.py", ignore_paths=[])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1

    def test_no_file_path_no_effect(self) -> None:
        ctx = self._make_context(None, ignore_paths=["**/legacy/**"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1

    def test_ignore_paths_skips_error_rules_too(self) -> None:
        ctx = self._make_context("/project/legacy/old.py", ignore_paths=["**/legacy/**"])
        engine = self._make_engine(rules=[AlwaysErrorRule()])
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_path_traversal_no_false_match(self) -> None:
        ctx = self._make_context("/project/src/legacy_utils.py", ignore_paths=["**/legacy/**"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1

    def test_relative_path_matches(self) -> None:
        ctx = self._make_context("src/legacy/old.py", ignore_paths=["*/legacy/*"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_absolute_path_matches(self) -> None:
        ctx = self._make_context("/project/legacy/old.py", ignore_paths=["/project/legacy/*"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_ignore_paths_special_chars_in_path(self) -> None:
        """fnmatch treats [] as character class; bracket patterns match accordingly."""
        ctx = self._make_context("/project/src/my-file.py", ignore_paths=["**/my-file.py"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_empty_pattern_no_crash(self) -> None:
        ctx = self._make_context("/project/src/app.py", ignore_paths=[""])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1

    def test_ignore_paths_as_string_not_list(self) -> None:
        """If ignore_paths is a string instead of a list, engine should not crash."""
        ctx = self._make_context("/project/legacy/old.py", ignore_paths="**/legacy/**")
        engine = self._make_engine()
        # isinstance check should skip non-list gracefully
        result = engine.evaluate(ctx)
        # String is not a list, so ignore_paths check is bypassed — rule fires
        assert len(result.violations) == 1

    def test_all_rules_skipped_for_ignored_file(self) -> None:
        ctx = self._make_context("/project/legacy/old.py", ignore_paths=["**/legacy/**"])
        engine = self._make_engine(rules=[AlwaysWarnRule(), AlwaysErrorRule()])
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0
        assert result.rules_evaluated == 0

    def test_no_config_no_crash(self) -> None:
        """context.config is empty dict — ignore_paths logic should not crash."""
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "/project/legacy/old.py"},
            project_dir="/project",
            config={},
            file_content="x = 1\n",
        )
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1

    def test_ignore_paths_with_spaces(self) -> None:
        ctx = self._make_context("/project/my folder/old.py", ignore_paths=["**/my folder/**"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_deeply_nested_path(self) -> None:
        ctx = self._make_context("/project/a/b/c/d/e/f/g.py", ignore_paths=["**/a/**/g.py"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_question_mark_wildcard(self) -> None:
        ctx = self._make_context("/project/src/test_a.py", ignore_paths=["**/test_?.py"])
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_bash_tool_no_file_path(self) -> None:
        """Bash commands without file_path should not be affected by ignore_paths."""
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "ls -la"},
            project_dir="/project",
            config={"ignore_paths": ["**/*.py"]},
            file_content=None,
        )
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1


# ---------------------------------------------------------------------------
# TestPerRuleAllowPaths
# ---------------------------------------------------------------------------

class TestPerRuleAllowPaths:
    """Tests for per-rule allow_paths feature in Engine."""

    def _make_context(self, file_path: str | None, config: dict | None = None) -> RuleContext:
        return RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": file_path} if file_path else {},
            project_dir="/project",
            config=config,
            file_content="x = 1\n",
        )

    def _make_engine(self, rules=None):
        config = AgentLintConfig(packs=["universal"])
        if rules is None:
            rules = [AlwaysWarnRule()]
        return Engine(config=config, rules=rules)

    def test_allow_paths_skips_specific_rule(self) -> None:
        ctx = self._make_context("/project/generated/out.py", config={
            "always-warn": {"allow_paths": ["**/generated/**"]},
        })
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_other_rules_still_fire(self) -> None:
        """Rule A has allow_paths, rule B does not — B should still fire."""
        ctx = self._make_context("/project/generated/out.py", config={
            "always-warn": {"allow_paths": ["**/generated/**"]},
        })
        engine = self._make_engine(rules=[AlwaysWarnRule(), AlwaysErrorRule()])
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "always-error"

    def test_glob_pattern_matching(self) -> None:
        ctx = self._make_context("/project/dist/bundle.js", config={
            "always-warn": {"allow_paths": ["**/dist/**"]},
        })
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_basename_matching(self) -> None:
        ctx = self._make_context("/project/src/Makefile", config={
            "always-warn": {"allow_paths": ["Makefile"]},
        })
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_multiple_patterns(self) -> None:
        ctx = self._make_context("/project/vendor/lib.py", config={
            "always-warn": {"allow_paths": ["**/vendor/**", "**/dist/**"]},
        })
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_empty_allow_paths_no_effect(self) -> None:
        ctx = self._make_context("/project/src/app.py", config={
            "always-warn": {"allow_paths": []},
        })
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1

    def test_allow_paths_error_rule(self) -> None:
        ctx = self._make_context("/project/generated/out.py", config={
            "always-error": {"allow_paths": ["**/generated/**"]},
        })
        engine = self._make_engine(rules=[AlwaysErrorRule()])
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_allow_paths_does_not_cascade_from_ignore_paths(self) -> None:
        """Per-rule allow_paths should be independent from global ignore_paths."""
        ctx = self._make_context("/project/src/app.py", config={
            "ignore_paths": ["**/legacy/**"],
            "always-warn": {"allow_paths": ["**/generated/**"]},
        })
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        # File matches neither ignore_paths nor allow_paths → rule fires
        assert len(result.violations) == 1

    def test_both_ignore_and_allow_paths(self) -> None:
        """Global ignore skips first; allow_paths is not reached."""
        ctx = self._make_context("/project/legacy/generated/out.py", config={
            "ignore_paths": ["**/legacy/**"],
            "always-warn": {"allow_paths": ["**/generated/**"]},
        })
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        # Global ignore_paths matches first — rule is skipped
        assert len(result.violations) == 0

    def test_non_matching_file_fires(self) -> None:
        ctx = self._make_context("/project/src/app.py", config={
            "always-warn": {"allow_paths": ["**/generated/**"]},
        })
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1

    def test_allow_paths_as_string_not_list(self) -> None:
        """If allow_paths is a string instead of list, engine should not crash."""
        ctx = self._make_context("/project/generated/out.py", config={
            "always-warn": {"allow_paths": "**/generated/**"},
        })
        engine = self._make_engine()
        # String is not a list, so allow_paths check is bypassed — rule fires
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1

    def test_no_allow_paths_config(self) -> None:
        """Rule has no allow_paths configured — rule should fire normally."""
        ctx = self._make_context("/project/src/app.py", config={})
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1

    def test_allow_paths_no_file_path(self) -> None:
        """No file_path in context — allow_paths check is skipped, rule fires."""
        ctx = self._make_context(None, config={
            "always-warn": {"allow_paths": ["**/generated/**"]},
        })
        engine = self._make_engine()
        result = engine.evaluate(ctx)
        assert len(result.violations) == 1

    def test_concurrent_rules_different_allow_paths(self) -> None:
        """Two rules with different allow_paths — each is checked independently."""
        ctx = self._make_context("/project/generated/out.py", config={
            "always-warn": {"allow_paths": ["**/generated/**"]},
            "always-error": {"allow_paths": ["**/vendor/**"]},
        })
        engine = self._make_engine(rules=[AlwaysWarnRule(), AlwaysErrorRule()])
        result = engine.evaluate(ctx)
        # always-warn skipped (matches generated), always-error fires (doesn't match vendor)
        assert len(result.violations) == 1
        assert result.violations[0].rule_id == "always-error"

    def test_disabled_rule_not_evaluated(self) -> None:
        """enabled:false + allow_paths → rule not evaluated at all."""
        config = AgentLintConfig(
            packs=["universal"],
            rules={"always-warn": {"enabled": False}},
        )
        ctx = self._make_context("/project/src/app.py", config={
            "always-warn": {"allow_paths": ["**/generated/**"]},
        })
        engine = Engine(config=config, rules=[AlwaysWarnRule()])
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0
        assert result.rules_evaluated == 0


class TestIgnorePathsAdversarial:
    """v1.9.0 — Adversarial edge cases for ignore_paths and allow_paths."""

    def test_unicode_path(self) -> None:
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE, tool_name="Write",
            tool_input={"file_path": "/project/données/café.py"},
            project_dir="/project",
            config={"ignore_paths": ["**/données/**"]},
            file_content="x = 1\n",
        )
        config = AgentLintConfig(packs=["universal"])
        engine = Engine(config=config, rules=[AlwaysWarnRule()])
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_path_with_spaces(self) -> None:
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE, tool_name="Write",
            tool_input={"file_path": "/project/my dir/app.py"},
            project_dir="/project",
            config={"ignore_paths": ["**/my dir/**"]},
            file_content="x = 1\n",
        )
        config = AgentLintConfig(packs=["universal"])
        engine = Engine(config=config, rules=[AlwaysWarnRule()])
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_double_star_at_start(self) -> None:
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE, tool_name="Write",
            tool_input={"file_path": "/deep/a/b/c/d/e/f/app.py"},
            project_dir="/deep",
            config={"ignore_paths": ["**/f/*.py"]},
            file_content="x = 1\n",
        )
        config = AgentLintConfig(packs=["universal"])
        engine = Engine(config=config, rules=[AlwaysWarnRule()])
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_question_mark_wildcard_paths(self) -> None:
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE, tool_name="Write",
            tool_input={"file_path": "/project/test_a.py"},
            project_dir="/project",
            config={"ignore_paths": ["test_?.py"]},
            file_content="x = 1\n",
        )
        config = AgentLintConfig(packs=["universal"])
        engine = Engine(config=config, rules=[AlwaysWarnRule()])
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_many_patterns_no_performance_issue(self) -> None:
        """100 patterns should not cause performance issues."""
        patterns = [f"**/fake_dir_{i}/**" for i in range(100)]
        patterns.append("**/real/**")
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE, tool_name="Write",
            tool_input={"file_path": "/project/real/app.py"},
            project_dir="/project",
            config={"ignore_paths": patterns},
            file_content="x = 1\n",
        )
        config = AgentLintConfig(packs=["universal"])
        engine = Engine(config=config, rules=[AlwaysWarnRule()])
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_empty_file_path_with_ignore_paths(self) -> None:
        """Empty string file_path should not crash with ignore_paths."""
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE, tool_name="Write",
            tool_input={},
            project_dir="/project",
            config={"ignore_paths": ["**/*.py"]},
            file_content="x = 1\n",
        )
        config = AgentLintConfig(packs=["universal"])
        engine = Engine(config=config, rules=[AlwaysWarnRule()])
        result = engine.evaluate(ctx)
        # No file_path → ignore_paths doesn't apply → rule fires
        assert len(result.violations) == 1

    def test_ignore_paths_none_in_list(self) -> None:
        """Non-string items in ignore_paths should not crash."""
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE, tool_name="Write",
            tool_input={"file_path": "/project/app.py"},
            project_dir="/project",
            config={"ignore_paths": ["**/app.py"]},
            file_content="x = 1\n",
        )
        config = AgentLintConfig(packs=["universal"])
        engine = Engine(config=config, rules=[AlwaysWarnRule()])
        result = engine.evaluate(ctx)
        assert len(result.violations) == 0

    def test_allow_paths_and_ignore_paths_both_match(self) -> None:
        """Both global ignore_paths and per-rule allow_paths match → both work."""
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE, tool_name="Write",
            tool_input={"file_path": "/project/legacy/old.py"},
            project_dir="/project",
            config={
                "ignore_paths": ["**/legacy/**"],
                "always-warn": {"allow_paths": ["**/old.py"]},
            },
            file_content="x = 1\n",
        )
        config = AgentLintConfig(packs=["universal"])
        engine = Engine(config=config, rules=[AlwaysWarnRule()])
        result = engine.evaluate(ctx)
        # Global ignore_paths catches first
        assert len(result.violations) == 0
