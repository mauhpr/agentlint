"""Rule: validate commit message format in git commit commands."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Extract message from: git commit -m "message" or git commit -m 'message'
_COMMIT_MSG_RE = re.compile(
    r"""\bgit\s+commit\b.*?-m\s+(?:"([^"]+)"|'([^']+)')""",
    re.IGNORECASE,
)

_CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|chore|docs|refactor|test|ci|style|perf|build|revert)(\(.+?\))?!?:\s.+",
)


class CommitMessageFormat(Rule):
    """Validate git commit message format."""

    id = "commit-message-format"
    description = "Validates commit messages follow conventional format"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "quality"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        match = _COMMIT_MSG_RE.search(command)
        if not match:
            return []

        message = match.group(1) or match.group(2)
        if not message:
            return []

        rule_config = context.config.get(self.id, {})
        max_length = rule_config.get("max_subject_length", 72)
        fmt = rule_config.get("format", "conventional")

        violations: list[Violation] = []

        # Subject line length check
        subject = message.split("\n")[0]
        if len(subject) > max_length:
            violations.append(
                Violation(
                    rule_id=self.id,
                    message=f"Commit subject exceeds {max_length} characters ({len(subject)})",
                    severity=self.severity,
                    suggestion=f"Keep the subject line under {max_length} characters.",
                )
            )

        # Conventional commits format check
        if fmt == "conventional" and not _CONVENTIONAL_RE.match(subject):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Commit message does not follow conventional format",
                    severity=self.severity,
                    suggestion="Use format: type(scope): description (e.g. feat: add login, fix(auth): token refresh)",
                )
            )

        return violations
