"""Rule: block catastrophic irreversible operations without explicit session confirmation."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Each tuple: (compiled_regex, label, confirmation_key).
_CATASTROPHIC_OPS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bDROP\s+DATABASE\b", re.IGNORECASE), "DROP DATABASE", "DROP DATABASE"),
    (re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE), "DROP TABLE", "DROP TABLE"),
    (re.compile(r"\bterraform\s+destroy\b", re.IGNORECASE), "terraform destroy", "terraform destroy"),
    (re.compile(r"\bkubectl\s+delete\s+namespace\b", re.IGNORECASE), "kubectl delete namespace", "kubectl delete namespace"),
    (re.compile(r"\bgcloud\s+projects?\s+delete\b", re.IGNORECASE), "gcloud projects delete", "gcloud projects delete"),
    (re.compile(r"\bheroku\s+apps?\s+destroy\b", re.IGNORECASE), "heroku apps destroy", "heroku apps destroy"),
]


class DestructiveConfirmationGate(Rule):
    """Block catastrophic irreversible ops unless session_state has explicit confirmation."""

    id = "destructive-confirmation-gate"
    description = "Blocks DROP DATABASE, terraform destroy, kubectl delete namespace without confirmation"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        confirmed: list[str] = context.session_state.get("confirmed_destructive_ops", [])
        confirmed_lower = [c.lower() for c in confirmed]

        for pattern, label, key in _CATASTROPHIC_OPS:
            if pattern.search(command):
                if key.lower() in confirmed_lower:
                    continue
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Catastrophic operation requires explicit confirmation: {label}",
                        severity=self.severity,
                        suggestion=(
                            f"Set session_state['confirmed_destructive_ops'] = ['{key}'] "
                            f"before running this command, or add it to destructive-confirmation-gate.bypass_ops in agentlint.yml."
                        ),
                    )
                ]

        return []
