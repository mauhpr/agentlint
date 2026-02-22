"""Rule: inject self-review prompt at session end."""
from __future__ import annotations

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_DEFAULT_PROMPT = (
    "Before finishing, review your changes as if you were a senior engineer "
    "who is skeptical of this code. Check for: logic errors, missing edge cases, "
    "security issues, test coverage gaps, and any assumptions you made that might be wrong."
)


class SelfReviewPrompt(Rule):
    """Inject an adversarial self-review prompt at session end."""

    id = "self-review-prompt"
    description = "Injects a self-review prompt at session end to catch bugs"
    severity = Severity.INFO
    events = [HookEvent.STOP]
    pack = "quality"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        rule_config = context.config.get(self.id, {})
        if not rule_config.get("enabled", True):
            return []

        prompt = rule_config.get("custom_prompt") or _DEFAULT_PROMPT

        return [
            Violation(
                rule_id=self.id,
                message=prompt,
                severity=self.severity,
            )
        ]
