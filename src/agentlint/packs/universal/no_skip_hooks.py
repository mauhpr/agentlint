"""Rule: warn on git commits that skip hooks or GPG signing."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

_NO_VERIFY_RE = re.compile(r"\bgit\s+commit\b.*--no-verify\b", re.IGNORECASE)
_NO_GPG_SIGN_RE = re.compile(r"\bgit\s+commit\b.*--no-gpg-sign\b", re.IGNORECASE)


class NoSkipHooks(Rule):
    """Warn on git commits that skip pre-commit hooks."""

    id = "no-skip-hooks"
    description = "Warns on git commit --no-verify or --no-gpg-sign"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        violations: list[Violation] = []

        if _NO_VERIFY_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="git commit --no-verify skips pre-commit hooks",
                    severity=self.severity,
                    suggestion="Remove --no-verify to run pre-commit hooks. Fix hook issues instead of bypassing them.",
                )
            )

        if _NO_GPG_SIGN_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="git commit --no-gpg-sign skips commit signing",
                    severity=self.severity,
                    suggestion="Remove --no-gpg-sign if your project requires signed commits.",
                )
            )

        return violations
