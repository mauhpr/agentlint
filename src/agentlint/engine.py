"""AgentLint evaluation engine."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agentlint.config import AgentLintConfig
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

        return result
