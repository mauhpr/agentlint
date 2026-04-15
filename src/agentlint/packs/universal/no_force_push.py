"""Rule: block force-push to main/master branches."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# --force (not --force-with-lease) targeting main or master.
_FORCE_PUSH_PROTECTED_RE = re.compile(
    r"git\s+push\b(?=.*(?:--force(?!-with-lease)|-f\b))(?=.*\b(main|master)\b)",
    re.IGNORECASE,
)

# --force-with-lease targeting main or master (safer variant).
_FORCE_LEASE_PROTECTED_RE = re.compile(
    r"git\s+push\b(?=.*--force-with-lease)(?=.*\b(main|master)\b)",
    re.IGNORECASE,
)

# --force (not --force-with-lease) to non-protected branches.
_FORCE_PUSH_ANY_RE = re.compile(
    r"git\s+push\b(?=.*(?:--force(?!-with-lease)|-f\b))(?!.*\b(?:main|master)\b)",
    re.IGNORECASE,
)

# --force-with-lease to non-protected branches.
_FORCE_LEASE_ANY_RE = re.compile(
    r"git\s+push\b(?=.*--force-with-lease)(?!.*\b(?:main|master)\b)",
    re.IGNORECASE,
)


class NoForcePush(Rule):
    """Block force-pushing to main or master branches."""

    id = "no-force-push"
    description = "Prevents force-pushing to main or master branches"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        # --force to protected branches: ERROR (most dangerous)
        match = _FORCE_PUSH_PROTECTED_RE.search(command)
        if match:
            branch = match.group(1)
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Force push to '{branch}' is blocked",
                    severity=Severity.ERROR,
                    suggestion=f"Never force-push to {branch}. Push to a feature branch instead.",
                )
            ]

        # --force-with-lease to protected branches: WARNING (safer but still risky)
        match = _FORCE_LEASE_PROTECTED_RE.search(command)
        if match:
            branch = match.group(1)
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Force push (with lease) to '{branch}' detected",
                    severity=Severity.WARNING,
                    suggestion=f"--force-with-lease is safer than --force, but pushing to {branch} is still risky.",
                )
            ]

        # --force to non-protected branches: WARNING
        if _FORCE_PUSH_ANY_RE.search(command):
            return [
                Violation(
                    rule_id=self.id,
                    message="Force push detected without explicit protected branch",
                    severity=Severity.WARNING,
                    suggestion="Specify the target branch explicitly. Avoid force-pushing to shared branches.",
                )
            ]

        # --force-with-lease to non-protected branches: INFO (low risk)
        if _FORCE_LEASE_ANY_RE.search(command):
            return [
                Violation(
                    rule_id=self.id,
                    message="Force push with lease detected",
                    severity=Severity.INFO,
                    suggestion="--force-with-lease is the safe variant. Proceed if the branch is yours.",
                )
            ]

        return []
