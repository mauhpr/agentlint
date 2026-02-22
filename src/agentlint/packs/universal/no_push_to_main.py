"""Rule: warn on direct push to main/master branches."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Matches `git push origin main` or `git push origin master` (non-force).
# Note: force pushes are already handled by no-force-push.
_PUSH_MAIN_RE = re.compile(
    r"\bgit\s+push\b(?!.*(?:--force(?:-with-lease)?|-f\b)).*\b(main|master)\b",
    re.IGNORECASE,
)


class NoPushToMain(Rule):
    """Warn on direct push to main or master branches."""

    id = "no-push-to-main"
    description = "Warns on direct push to main or master branches"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        match = _PUSH_MAIN_RE.search(command)
        if match:
            branch = match.group(1)
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Direct push to '{branch}' detected",
                    severity=self.severity,
                    suggestion=f"Push to a feature branch and create a pull request instead of pushing directly to {branch}.",
                )
            ]

        return []
