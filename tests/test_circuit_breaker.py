"""Tests for circuit breaker module."""
from __future__ import annotations

import time

from agentlint.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerState,
    _CB_NEVER_DEGRADE,
    _downgrade_severity,
    _get_cb_config,
    _get_rule_state,
    apply_circuit_breaker,
)
from agentlint.models import Severity, Violation


# --- CircuitBreakerState tests ---


class TestCircuitBreakerState:
    def test_active_value(self) -> None:
        assert CircuitBreakerState.ACTIVE.value == "active"

    def test_degraded_value(self) -> None:
        assert CircuitBreakerState.DEGRADED.value == "degraded"

    def test_passive_value(self) -> None:
        assert CircuitBreakerState.PASSIVE.value == "passive"

    def test_open_value(self) -> None:
        assert CircuitBreakerState.OPEN.value == "open"

    def test_all_states_exist(self) -> None:
        assert len(CircuitBreakerState) == 4


# --- CircuitBreakerConfig tests ---


class TestCircuitBreakerConfig:
    def test_defaults(self) -> None:
        cfg = CircuitBreakerConfig()
        assert cfg.enabled is True
        assert cfg.degraded_after == 3
        assert cfg.passive_after == 6
        assert cfg.open_after == 10
        assert cfg.reset_after_clean == 5
        assert cfg.reset_after_minutes == 30

    def test_can_disable(self) -> None:
        cfg = CircuitBreakerConfig(enabled=False)
        assert cfg.enabled is False

    def test_custom_thresholds(self) -> None:
        cfg = CircuitBreakerConfig(
            degraded_after=5,
            passive_after=10,
            open_after=20,
            reset_after_clean=3,
            reset_after_minutes=60,
        )
        assert cfg.degraded_after == 5
        assert cfg.passive_after == 10
        assert cfg.open_after == 20
        assert cfg.reset_after_clean == 3
        assert cfg.reset_after_minutes == 60


# --- apply_circuit_breaker tests ---


class TestApplyCircuitBreaker:
    def _make_violation(
        self,
        rule_id: str = "test-rule",
        severity: Severity = Severity.ERROR,
        message: str = "test violation",
    ) -> Violation:
        return Violation(rule_id=rule_id, message=message, severity=severity)

    def test_first_fire_stays_active(self) -> None:
        """First ERROR violation stays ERROR — state remains ACTIVE."""
        session: dict = {}
        violations = [self._make_violation()]
        result = apply_circuit_breaker(violations, session, {})
        assert len(result) == 1
        assert result[0].severity == Severity.ERROR
        cb_data = session["circuit_breaker"]["test-rule"]
        assert cb_data["fire_count"] == 1
        assert cb_data["state"] == "active"

    def test_degrades_after_threshold(self) -> None:
        """After 3 fires, ERROR degrades to WARNING."""
        session: dict = {"circuit_breaker": {
            "test-rule": {
                "fire_count": 2,
                "clean_count": 0,
                "first_fire_ts": time.time() - 60,
                "last_fire_ts": time.time() - 30,
                "state": "active",
                "transitions": [],
            },
        }}
        violations = [self._make_violation()]
        result = apply_circuit_breaker(violations, session, {})
        assert len(result) == 1
        assert result[0].severity == Severity.WARNING
        assert session["circuit_breaker"]["test-rule"]["state"] == "degraded"

    def test_passive_after_threshold(self) -> None:
        """After 6 fires, ERROR degrades to INFO."""
        session: dict = {"circuit_breaker": {
            "test-rule": {
                "fire_count": 5,
                "clean_count": 0,
                "first_fire_ts": time.time() - 300,
                "last_fire_ts": time.time() - 30,
                "state": "degraded",
                "transitions": [],
            },
        }}
        violations = [self._make_violation()]
        result = apply_circuit_breaker(violations, session, {})
        assert len(result) == 1
        assert result[0].severity == Severity.INFO
        assert session["circuit_breaker"]["test-rule"]["state"] == "passive"

    def test_open_after_threshold(self) -> None:
        """After 10 fires, violations are suppressed entirely."""
        session: dict = {"circuit_breaker": {
            "test-rule": {
                "fire_count": 9,
                "clean_count": 0,
                "first_fire_ts": time.time() - 600,
                "last_fire_ts": time.time() - 30,
                "state": "passive",
                "transitions": [],
            },
        }}
        violations = [self._make_violation()]
        result = apply_circuit_breaker(violations, session, {})
        assert len(result) == 0
        assert session["circuit_breaker"]["test-rule"]["state"] == "open"

    def test_clean_evaluations_reset(self) -> None:
        """Clean evaluations (no violations for a tracked rule) increment
        clean_count and eventually reset the circuit breaker."""
        session: dict = {"circuit_breaker": {
            "test-rule": {
                "fire_count": 4,
                "clean_count": 4,
                "first_fire_ts": time.time() - 300,
                "last_fire_ts": time.time() - 60,
                "state": "degraded",
                "transitions": [],
            },
        }}
        # No violations means a clean evaluation — pass empty list
        result = apply_circuit_breaker([], session, {})
        cb_data = session["circuit_breaker"]["test-rule"]
        # After reaching reset_after_clean, the breaker resets entirely
        assert cb_data["clean_count"] == 0
        assert cb_data["state"] == "active"
        assert cb_data["fire_count"] == 0
        assert len(result) == 0

    def test_disabled_cb_passes_through(self) -> None:
        """When circuit breaker is disabled, violations pass unchanged."""
        session: dict = {}
        rules_config = {
            "test-rule": {"circuit_breaker": {"enabled": False}},
        }
        violations = [self._make_violation()]
        # Fire many times — should never degrade
        for _ in range(15):
            result = apply_circuit_breaker(violations, session, rules_config)
        assert len(result) == 1
        assert result[0].severity == Severity.ERROR

    def test_security_rules_never_degrade(self) -> None:
        """Security-critical rules like no-secrets never degrade."""
        session: dict = {}
        violations = [self._make_violation(rule_id="no-secrets")]
        # Fire 20 times — should always stay ERROR
        for i in range(20):
            result = apply_circuit_breaker(violations, session, {})
            assert len(result) == 1
            assert result[0].severity == Severity.ERROR
        cb_data = session["circuit_breaker"]["no-secrets"]
        assert cb_data["fire_count"] == 20
        assert cb_data["state"] == "active"

    def test_multiple_rules_tracked_independently(self) -> None:
        """Each rule has its own circuit breaker tracking."""
        session: dict = {}
        v_a = self._make_violation(rule_id="rule-a")
        v_b = self._make_violation(rule_id="rule-b")

        # Fire rule-a 4 times (should degrade)
        for _ in range(4):
            apply_circuit_breaker([v_a], session, {})

        # Fire rule-b once (should stay active)
        apply_circuit_breaker([v_b], session, {})

        assert session["circuit_breaker"]["rule-a"]["fire_count"] == 4
        assert session["circuit_breaker"]["rule-a"]["state"] == "degraded"
        assert session["circuit_breaker"]["rule-b"]["fire_count"] == 1
        assert session["circuit_breaker"]["rule-b"]["state"] == "active"

    def test_per_rule_config_override(self) -> None:
        """Per-rule config can override global thresholds."""
        session: dict = {}
        rules_config = {
            "test-rule": {"circuit_breaker": {"degraded_after": 5}},
        }
        violations = [self._make_violation()]

        # After 3 fires (default threshold) should still be active with custom config
        for _ in range(3):
            result = apply_circuit_breaker(violations, session, rules_config)
        assert result[0].severity == Severity.ERROR
        assert session["circuit_breaker"]["test-rule"]["state"] == "active"

        # After 5 fires should degrade
        for _ in range(2):
            result = apply_circuit_breaker(violations, session, rules_config)
        assert result[0].severity == Severity.WARNING
        assert session["circuit_breaker"]["test-rule"]["state"] == "degraded"

    def test_warning_violations_not_affected(self) -> None:
        """WARNING violations pass through untouched by circuit breaker."""
        session: dict = {}
        violations = [self._make_violation(severity=Severity.WARNING)]

        # Fire many times — WARNING should never change
        for _ in range(15):
            result = apply_circuit_breaker(violations, session, {})
            assert len(result) == 1
            assert result[0].severity == Severity.WARNING

    def test_info_violations_not_affected(self) -> None:
        """INFO violations pass through untouched by circuit breaker."""
        session: dict = {}
        violations = [self._make_violation(severity=Severity.INFO)]

        for _ in range(15):
            result = apply_circuit_breaker(violations, session, {})
            assert len(result) == 1
            assert result[0].severity == Severity.INFO

    def test_time_based_reset(self) -> None:
        """Circuit breaker resets after reset_after_minutes even without
        clean evaluations."""
        session: dict = {"circuit_breaker": {
            "test-rule": {
                "fire_count": 5,
                "clean_count": 0,
                "first_fire_ts": time.time() - 3600,  # 1 hour ago
                "last_fire_ts": time.time() - 3600,
                "state": "degraded",
                "transitions": [],
            },
        }}
        violations = [self._make_violation()]
        result = apply_circuit_breaker(violations, session, {})
        # Should have reset, so this is fire_count=1 → ACTIVE → ERROR
        assert len(result) == 1
        assert result[0].severity == Severity.ERROR
        assert session["circuit_breaker"]["test-rule"]["state"] == "active"
        assert session["circuit_breaker"]["test-rule"]["fire_count"] == 1

    def test_never_degrade_set_contents(self) -> None:
        """Verify the _CB_NEVER_DEGRADE set has the expected members."""
        assert "no-secrets" in _CB_NEVER_DEGRADE
        assert "no-env-commit" in _CB_NEVER_DEGRADE

    def test_no_env_commit_never_degrades(self) -> None:
        """no-env-commit is also security-critical and never degrades."""
        session: dict = {}
        violations = [self._make_violation(rule_id="no-env-commit")]
        for _ in range(20):
            result = apply_circuit_breaker(violations, session, {})
            assert len(result) == 1
            assert result[0].severity == Severity.ERROR

    def test_mixed_severity_violations(self) -> None:
        """When a rule emits both ERROR and WARNING, only ERROR is affected."""
        session: dict = {"circuit_breaker": {
            "test-rule": {
                "fire_count": 2,
                "clean_count": 0,
                "first_fire_ts": time.time() - 60,
                "last_fire_ts": time.time() - 30,
                "state": "active",
                "transitions": [],
            },
        }}
        violations = [
            self._make_violation(severity=Severity.ERROR, message="error one"),
            self._make_violation(severity=Severity.WARNING, message="warn one"),
        ]
        result = apply_circuit_breaker(violations, session, {})
        error_results = [v for v in result if "error one" in v.message]
        warning_results = [v for v in result if v.message == "warn one"]
        # ERROR should be downgraded to WARNING (3rd fire = degraded)
        assert error_results[0].severity == Severity.WARNING
        # Degraded message should include circuit breaker context
        assert "Circuit breaker" in error_results[0].message
        # WARNING should remain WARNING
        assert warning_results[0].severity == Severity.WARNING

    def test_transitions_recorded(self) -> None:
        """State transitions are recorded in the transitions list."""
        session: dict = {"circuit_breaker": {
            "test-rule": {
                "fire_count": 2,
                "clean_count": 0,
                "first_fire_ts": time.time() - 60,
                "last_fire_ts": time.time() - 30,
                "state": "active",
                "transitions": [],
            },
        }}
        violations = [self._make_violation()]
        apply_circuit_breaker(violations, session, {})
        transitions = session["circuit_breaker"]["test-rule"]["transitions"]
        assert len(transitions) == 1
        assert transitions[0]["from"] == "active"
        assert transitions[0]["to"] == "degraded"


# --- Helper function tests ---


class TestGetCbConfig:
    def test_global_defaults(self) -> None:
        """Without any overrides, returns default config."""
        cfg = _get_cb_config("test-rule", {})
        assert cfg.enabled is True
        assert cfg.degraded_after == 3

    def test_per_rule_override(self) -> None:
        """Per-rule circuit_breaker key overrides defaults."""
        rules_config = {
            "test-rule": {"circuit_breaker": {"degraded_after": 7, "enabled": False}},
        }
        cfg = _get_cb_config("test-rule", rules_config)
        assert cfg.enabled is False
        assert cfg.degraded_after == 7
        # Non-overridden fields keep defaults
        assert cfg.passive_after == 6

    def test_missing_rule_config(self) -> None:
        """Rule not in rules_config returns defaults."""
        cfg = _get_cb_config("unknown-rule", {"other-rule": {}})
        assert cfg.enabled is True


class TestGetRuleState:
    def test_active_below_degraded(self) -> None:
        cfg = CircuitBreakerConfig()
        cb_data = {"fire_count": 2}
        assert _get_rule_state(cb_data, cfg) == CircuitBreakerState.ACTIVE

    def test_degraded_at_threshold(self) -> None:
        cfg = CircuitBreakerConfig()
        cb_data = {"fire_count": 3}
        assert _get_rule_state(cb_data, cfg) == CircuitBreakerState.DEGRADED

    def test_passive_at_threshold(self) -> None:
        cfg = CircuitBreakerConfig()
        cb_data = {"fire_count": 6}
        assert _get_rule_state(cb_data, cfg) == CircuitBreakerState.PASSIVE

    def test_open_at_threshold(self) -> None:
        cfg = CircuitBreakerConfig()
        cb_data = {"fire_count": 10}
        assert _get_rule_state(cb_data, cfg) == CircuitBreakerState.OPEN

    def test_beyond_open(self) -> None:
        cfg = CircuitBreakerConfig()
        cb_data = {"fire_count": 100}
        assert _get_rule_state(cb_data, cfg) == CircuitBreakerState.OPEN


class TestDowngradeSeverity:
    def test_active_no_change(self) -> None:
        assert _downgrade_severity(Severity.ERROR, CircuitBreakerState.ACTIVE) == Severity.ERROR

    def test_degraded_error_to_warning(self) -> None:
        assert _downgrade_severity(Severity.ERROR, CircuitBreakerState.DEGRADED) == Severity.WARNING

    def test_passive_error_to_info(self) -> None:
        assert _downgrade_severity(Severity.ERROR, CircuitBreakerState.PASSIVE) == Severity.INFO

    def test_open_returns_none(self) -> None:
        assert _downgrade_severity(Severity.ERROR, CircuitBreakerState.OPEN) is None

    def test_warning_unchanged_in_degraded(self) -> None:
        assert _downgrade_severity(Severity.WARNING, CircuitBreakerState.DEGRADED) == Severity.WARNING

    def test_info_unchanged_in_degraded(self) -> None:
        assert _downgrade_severity(Severity.INFO, CircuitBreakerState.DEGRADED) == Severity.INFO


# --- Edge case / defensive coding tests ---


class TestCircuitBreakerEdgeCases:
    def _make_violation(
        self,
        rule_id: str = "test-rule",
        severity: Severity = Severity.ERROR,
        message: str = "test violation",
    ) -> Violation:
        return Violation(rule_id=rule_id, message=message, severity=severity)

    def test_corrupted_state_recovers(self) -> None:
        """Invalid state string in session JSON doesn't crash — defaults to ACTIVE."""
        session: dict = {"circuit_breaker": {
            "test-rule": {
                "fire_count": 2,
                "clean_count": 0,
                "first_fire_ts": time.time() - 60,
                "last_fire_ts": time.time() - 30,
                "state": "garbage_invalid_state",
                "transitions": [],
            },
        }}
        violations = [self._make_violation()]
        # Should not raise — recovers to ACTIVE
        result = apply_circuit_breaker(violations, session, {})
        assert len(result) == 1
        # fire_count becomes 3 → DEGRADED, but corrupted state defaults to ACTIVE
        # first, so the effective state after recovery depends on the new state calc
        cb_data = session["circuit_breaker"]["test-rule"]
        assert cb_data["state"] in {"active", "degraded"}

    def test_missing_fire_count_key_recovers(self) -> None:
        """Missing 'fire_count' key in cb_data doesn't crash."""
        session: dict = {"circuit_breaker": {
            "test-rule": {
                # fire_count intentionally missing
                "clean_count": 0,
                "first_fire_ts": time.time() - 60,
                "last_fire_ts": time.time() - 30,
                "state": "active",
                "transitions": [],
            },
        }}
        violations = [self._make_violation()]
        # Should not raise — .get() defaults to 0
        result = apply_circuit_breaker(violations, session, {})
        assert len(result) == 1
        assert result[0].severity == Severity.ERROR
        assert session["circuit_breaker"]["test-rule"]["fire_count"] == 1

    def test_zero_threshold_degrades_immediately(self) -> None:
        """degraded_after=0 means every fire is immediately degraded."""
        session: dict = {}
        rules_config = {
            "test-rule": {"circuit_breaker": {
                "degraded_after": 0,
                "passive_after": 0,
                "open_after": 1,
            }},
        }
        violations = [self._make_violation()]
        # First fire: fire_count=1 >= open_after=1 → OPEN → suppressed
        result = apply_circuit_breaker(violations, session, rules_config)
        assert len(result) == 0

    def test_protected_rule_check_before_enabled(self) -> None:
        """Security rules (no-secrets) are protected even if CB is set to disabled.

        This is a regression test for the security bypass fix: the protected-rule
        check must happen before the enabled check to prevent config from
        accidentally disabling protection on security-critical rules.
        """
        session: dict = {}
        rules_config = {
            "no-secrets": {"circuit_breaker": {"enabled": False}},
        }
        violations = [self._make_violation(rule_id="no-secrets")]
        # Fire 15 times with CB disabled — should still always return ERROR
        for _ in range(15):
            result = apply_circuit_breaker(violations, session, rules_config)
            assert len(result) == 1
            assert result[0].severity == Severity.ERROR

    def test_degraded_violation_message_includes_context(self) -> None:
        """When a violation is degraded, the message includes CB context."""
        session: dict = {"circuit_breaker": {
            "test-rule": {
                "fire_count": 2,
                "clean_count": 0,
                "first_fire_ts": time.time() - 60,
                "last_fire_ts": time.time() - 30,
                "state": "active",
                "transitions": [],
            },
        }}
        violations = [self._make_violation(message="original msg")]
        result = apply_circuit_breaker(violations, session, {})
        assert len(result) == 1
        # Should be degraded (3rd fire)
        assert result[0].severity == Severity.WARNING
        # Message should contain circuit breaker context
        assert "[Circuit breaker:" in result[0].message
        assert "fired 3x" in result[0].message
        assert "degraded from error to warning" in result[0].message
        # Original message should still be present
        assert "original msg" in result[0].message
