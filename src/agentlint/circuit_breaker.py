"""Circuit breaker for AgentLint rules.

Prevents buggy or overly-noisy rules from blocking agents repeatedly.
Tracks per-rule fire counts in session state and progressively degrades
ERROR violations through WARNING -> INFO -> suppressed based on
configurable thresholds.

Security-critical rules (defined in _CB_NEVER_DEGRADE) are exempt and
always maintain their original severity.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum

from agentlint.models import Severity, Violation

logger = logging.getLogger("agentlint")

# Security-critical rules that must never be degraded or suppressed.
_CB_NEVER_DEGRADE: set[str] = {"no-secrets", "no-env-commit"}


class CircuitBreakerState(Enum):
    """Progressive states for a rule's circuit breaker."""

    ACTIVE = "active"
    DEGRADED = "degraded"
    PASSIVE = "passive"
    OPEN = "open"


@dataclass
class CircuitBreakerConfig:
    """Configuration for the circuit breaker behaviour."""

    enabled: bool = True
    degraded_after: int = 3
    passive_after: int = 6
    open_after: int = 10
    reset_after_clean: int = 5
    reset_after_minutes: int = 30


def _get_cb_config(rule_id: str, rules_config: dict) -> CircuitBreakerConfig:
    """Build a CircuitBreakerConfig from global defaults + per-rule overrides."""
    global_cb = rules_config.get("_circuit_breaker_global", {})
    rule_cb = rules_config.get(rule_id, {}).get("circuit_breaker", {})
    merged = {**global_cb, **rule_cb}
    return CircuitBreakerConfig(**{
        k: v
        for k, v in merged.items()
        if k in CircuitBreakerConfig.__dataclass_fields__
    })


def _get_rule_state(cb_data: dict, config: CircuitBreakerConfig) -> CircuitBreakerState:
    """Determine circuit breaker state from fire count."""
    fire_count = cb_data.get("fire_count", 0)
    if fire_count >= config.open_after:
        return CircuitBreakerState.OPEN
    if fire_count >= config.passive_after:
        return CircuitBreakerState.PASSIVE
    if fire_count >= config.degraded_after:
        return CircuitBreakerState.DEGRADED
    return CircuitBreakerState.ACTIVE


def _downgrade_severity(
    severity: Severity, state: CircuitBreakerState
) -> Severity | None:
    """Map severity based on circuit breaker state.

    Only ERROR severity is affected. WARNING and INFO pass through unchanged.
    Returns None for OPEN state (violation should be suppressed).
    """
    if severity != Severity.ERROR:
        return severity

    if state == CircuitBreakerState.ACTIVE:
        return Severity.ERROR
    if state == CircuitBreakerState.DEGRADED:
        return Severity.WARNING
    if state == CircuitBreakerState.PASSIVE:
        return Severity.INFO
    # OPEN
    return None


def _make_default_cb_data() -> dict:
    """Return a fresh per-rule circuit breaker tracking dict."""
    return {
        "fire_count": 0,
        "clean_count": 0,
        "first_fire_ts": None,
        "last_fire_ts": None,
        "state": CircuitBreakerState.ACTIVE.value,
        "transitions": [],
    }


def _should_reset_by_time(cb_data: dict, config: CircuitBreakerConfig) -> bool:
    """Check if enough time has elapsed to reset the circuit breaker."""
    last_fire = cb_data.get("last_fire_ts")
    if last_fire is None:
        return False
    elapsed_minutes = (time.time() - last_fire) / 60
    return elapsed_minutes >= config.reset_after_minutes


def _reset_cb_data(cb_data: dict, rule_id: str = "unknown") -> None:
    """Reset a rule's circuit breaker tracking data to initial state."""
    old_state = cb_data.get("state", CircuitBreakerState.ACTIVE.value)
    cb_data["fire_count"] = 0
    cb_data["clean_count"] = 0
    cb_data["first_fire_ts"] = None
    cb_data["last_fire_ts"] = None
    new_state = CircuitBreakerState.ACTIVE.value
    if old_state != new_state:
        cb_data.setdefault("transitions", []).append({
            "from": old_state,
            "to": new_state,
            "ts": time.time(),
            "reason": "reset",
        })
        logger.debug(
            "Circuit breaker: %s reset to active (from=%s)", rule_id, old_state,
        )
    cb_data["state"] = new_state


def apply_circuit_breaker(
    violations: list[Violation],
    session_state: dict,
    rules_config: dict,
) -> list[Violation]:
    """Apply circuit breaker logic to a list of violations.

    Tracks per-rule fire counts in session_state["circuit_breaker"].
    ERROR violations are progressively degraded (WARNING -> INFO -> suppressed)
    based on fire count thresholds. WARNING and INFO violations pass through
    untouched. Security-critical rules never degrade.

    When no violations are present for a tracked rule, its clean_count is
    incremented; after enough clean evaluations the breaker resets.

    Args:
        violations: List of Violation objects from rule evaluation.
        session_state: Mutable session dict (modified in place).
        rules_config: Per-rule configuration dict (from AgentLintConfig.rules).

    Returns:
        Filtered/modified list of violations.
    """
    if "circuit_breaker" not in session_state:
        session_state["circuit_breaker"] = {}

    cb_store = session_state["circuit_breaker"]
    now = time.time()

    # Collect which rules fired in this evaluation
    fired_rule_ids: set[str] = set()
    for v in violations:
        if v.severity == Severity.ERROR:
            fired_rule_ids.add(v.rule_id)

    # Handle clean evaluations for tracked rules that did NOT fire
    for rule_id, cb_data in list(cb_store.items()):
        if rule_id in fired_rule_ids:
            continue
        config = _get_cb_config(rule_id, rules_config)
        if not config.enabled:
            continue
        cb_data["clean_count"] = cb_data.get("clean_count", 0) + 1
        if cb_data["clean_count"] >= config.reset_after_clean:
            _reset_cb_data(cb_data, rule_id=rule_id)

    # Process violations
    result: list[Violation] = []
    for v in violations:
        # Security-critical rules are ALWAYS protected — check before anything else
        is_protected = v.rule_id in _CB_NEVER_DEGRADE

        config = _get_cb_config(v.rule_id, rules_config)

        # If CB is disabled for this rule, pass through unchanged.
        # Protected rules skip this check — they are always tracked.
        if not is_protected and not config.enabled:
            result.append(v)
            continue

        # Only ERROR violations are tracked and affected by CB
        if v.severity != Severity.ERROR:
            result.append(v)
            continue

        # Ensure tracking entry exists
        if v.rule_id not in cb_store:
            cb_store[v.rule_id] = _make_default_cb_data()

        cb_data = cb_store[v.rule_id]

        # Time-based reset: if enough time has passed since last fire, reset
        if _should_reset_by_time(cb_data, config):
            _reset_cb_data(cb_data, rule_id=v.rule_id)

        # Increment fire count
        cb_data["fire_count"] = cb_data.get("fire_count", 0) + 1
        cb_data["clean_count"] = 0
        if cb_data.get("first_fire_ts") is None:
            cb_data["first_fire_ts"] = now
        cb_data["last_fire_ts"] = now

        # Determine new state
        new_state = _get_rule_state(cb_data, config)

        # Record transition if state changed
        old_state_str = cb_data.get("state", CircuitBreakerState.ACTIVE.value)
        new_state_str = new_state.value
        if old_state_str != new_state_str:
            if not is_protected:
                cb_data.setdefault("transitions", []).append({
                    "from": old_state_str,
                    "to": new_state_str,
                    "ts": now,
                    "reason": "fire_count",
                })
                cb_data["state"] = new_state_str
                logger.info(
                    "Circuit breaker: %s transitioned %s -> %s (fire_count=%d)",
                    v.rule_id, old_state_str, new_state_str, cb_data["fire_count"],
                )

        # For protected rules, always keep ACTIVE state and original severity
        if is_protected:
            cb_data["state"] = CircuitBreakerState.ACTIVE.value
            result.append(v)
            continue

        # Apply severity downgrade based on state
        try:
            effective_state = CircuitBreakerState(cb_data["state"])
        except (KeyError, ValueError):
            effective_state = CircuitBreakerState.ACTIVE
            cb_data["state"] = CircuitBreakerState.ACTIVE.value
        new_severity = _downgrade_severity(v.severity, effective_state)

        if new_severity is None:
            # OPEN state — suppress the violation
            logger.info(
                "Circuit breaker: suppressing %s (fire_count=%d, state=open)",
                v.rule_id, cb_data["fire_count"],
            )
            continue

        # Build message with degradation context if severity changed
        msg = v.message
        if new_severity != v.severity:
            msg = (
                f"[Circuit breaker: fired {cb_data['fire_count']}x, "
                f"degraded from {v.severity.value} to {new_severity.value}] "
                f"{v.message}"
            )

        # Return a new violation with the downgraded severity
        result.append(Violation(
            rule_id=v.rule_id,
            message=msg,
            severity=new_severity,
            file_path=v.file_path,
            line=v.line,
            suggestion=v.suggestion,
        ))

    return result
