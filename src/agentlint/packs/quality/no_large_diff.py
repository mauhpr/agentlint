"""Rule: warn when a single Write/Edit produces a large diff.

Forces the agent to work in smaller, reviewable chunks. Uses
file_content_before (cached by PreToolUse) to compute diff size.
"""
from __future__ import annotations

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_DEFAULT_MAX_ADDED = 200
_DEFAULT_MAX_REMOVED = 100


class NoLargeDiff(Rule):
    id = "no-large-diff"
    description = "Warns when a single edit adds or removes too many lines"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE]
    pack = "quality"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in ("Write", "Edit"):
            return []

        content_after = context.file_content
        content_before = context.file_content_before

        if content_after is None:
            return []

        rule_config = context.config.get(self.id, {})
        max_added = rule_config.get("max_lines_added", _DEFAULT_MAX_ADDED)
        max_removed = rule_config.get("max_lines_removed", _DEFAULT_MAX_REMOVED)

        lines_after = content_after.splitlines()
        lines_before = content_before.splitlines() if content_before else []

        added = max(0, len(lines_after) - len(lines_before))
        removed = max(0, len(lines_before) - len(lines_after))

        violations: list[Violation] = []

        if added > max_added:
            violations.append(Violation(
                rule_id=self.id,
                message=f"{added} lines added in a single edit (max {max_added})",
                severity=self.severity,
                file_path=context.file_path,
                suggestion="Break into smaller, reviewable changes",
            ))

        if removed > max_removed:
            violations.append(Violation(
                rule_id=self.id,
                message=f"{removed} lines removed in a single edit (max {max_removed})",
                severity=self.severity,
                file_path=context.file_path,
                suggestion="Review large deletions carefully before proceeding",
            ))

        return violations
