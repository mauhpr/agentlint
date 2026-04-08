"""AgentLint evaluation engine."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agentlint.circuit_breaker import apply_circuit_breaker
from agentlint.config import AgentLintConfig, get_rule_setting
from agentlint.models import Rule, RuleContext, Severity, Violation

logger = logging.getLogger("agentlint")


@dataclass
class EvaluationResult:
    """Result of evaluating rules against a context."""
    violations: list[Violation] = field(default_factory=list)
    rules_evaluated: int = 0

    @property
    def is_blocking(self) -> bool:
        return any(v.severity == Severity.ERROR for v in self.violations)


class Engine:
    """Orchestrates rule loading and evaluation."""

    def __init__(self, config: AgentLintConfig, rules: list[Rule]):
        self.config = config
        self.rules = rules

    def evaluate(self, context: RuleContext) -> EvaluationResult:
        """Evaluate all applicable rules against the context."""
        result = EvaluationResult()

        for rule in self.rules:
            if rule.pack not in self.config.packs:
                continue
            if not self.config.is_rule_enabled(rule.id):
                continue
            if not rule.matches_event(context.event):
                continue

            result.rules_evaluated += 1

            try:
                violations = rule.evaluate(context)
            except Exception:
                logger.exception("Rule %s raised an exception", rule.id)
                continue

            for v in violations:
                v.severity = self.config.effective_severity(v.severity)

            result.violations.extend(violations)

        # Apply circuit breaker degradation
        result.violations = apply_circuit_breaker(
            result.violations, context.session_state, context.config,
        )

        # Suppress acknowledged rules (ERRORs are never suppressed)
        suppressed = set(context.session_state.get("suppressed_rules", []))
        if suppressed:
            result.violations = [
                v for v in result.violations
                if v.rule_id not in suppressed or v.severity == Severity.ERROR
            ]

        # Auto-suppress: track consecutive fires per rule (after manual suppress
        # filter so already-suppressed rules don't accumulate counts)
        auto_suppress_threshold = context.config.get("auto_suppress_after", 0) if context.config else 0
        if auto_suppress_threshold and auto_suppress_threshold > 0:
            fire_counts = context.session_state.setdefault("rule_fire_counts", {})
            # Count once per rule per invocation, not per violation
            fired_non_error_ids: set[str] = {
                v.rule_id for v in result.violations if v.severity != Severity.ERROR
            }
            for rule_id in fired_non_error_ids:
                count = fire_counts.get(rule_id, 0) + 1
                fire_counts[rule_id] = count
                threshold = get_rule_setting(
                    context.config, rule_id, "auto_suppress_after", auto_suppress_threshold,
                )
                if count > threshold:
                    suppressed_rules = context.session_state.setdefault("suppressed_rules", [])
                    if rule_id not in suppressed_rules:
                        suppressed_rules.append(rule_id)
                        logger.info("Auto-suppressed '%s' after %d fires", rule_id, count)
            # Reset count for rules that didn't fire
            for rid in list(fire_counts):
                if rid not in fired_non_error_ids:
                    fire_counts[rid] = 0

            # Filter newly auto-suppressed violations from this evaluation
            newly_suppressed = set(context.session_state.get("suppressed_rules", [])) - suppressed
            if newly_suppressed:
                result.violations = [
                    v for v in result.violations
                    if v.rule_id not in newly_suppressed or v.severity == Severity.ERROR
                ]

        return result
