"""Rule: block force-push to main/master branches."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Matches `git push` with --force, --force-with-lease, or -f targeting main or master.
_FORCE_PUSH_PROTECTED_RE = re.compile(
    r"git\s+push\b(?=.*(?:--force(?:-with-lease)?|-f\b))(?=.*\b(main|master)\b)",
    re.IGNORECASE,
)

# Matches any force push (no explicit branch — could push current branch).
_FORCE_PUSH_ANY_RE = re.compile(
    r"git\s+push\b(?=.*(?:--force(?:-with-lease)?|-f\b))(?!.*\b(?:main|master)\b)",
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

        # Block force-push to protected branches (ERROR).
        match = _FORCE_PUSH_PROTECTED_RE.search(command)
        if match:
            branch = match.group(1)
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Force push to '{branch}' is blocked",
                    severity=self.severity,
                    suggestion=f"Never force-push to {branch}. Push to a feature branch instead.",
                )
            ]

        # Warn on force-push without explicit protected branch (could push current branch).
        if _FORCE_PUSH_ANY_RE.search(command):
            return [
                Violation(
                    rule_id=self.id,
                    message="Force push detected without explicit branch",
                    severity=Severity.WARNING,
                    suggestion="Specify the target branch explicitly. Avoid force-pushing to shared branches.",
                )
            ]

        return []
