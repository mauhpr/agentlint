"""Rule: focus indicator removed without replacement (WCAG 2.4.7)."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.frontend._helpers import _WRITE_TOOLS, is_frontend_file

_OUTLINE_NONE_RE = re.compile(r"\boutline-none\b")
_FOCUS_RING_RE = re.compile(r"\bfocus(?:-visible)?:ring-")


class StyleFocusVisible(Rule):
    """Focus indicator removed without replacement (WCAG 2.4.7)."""

    id = "style-focus-visible"
    description = "Ensures focus indicators are not removed without replacement"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "frontend"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []
        if not is_frontend_file(context.file_path):
            return []

        content = context.tool_input.get("content", "")
        if not content:
            return []

        violations: list[Violation] = []

        for line_num, line in enumerate(content.splitlines(), start=1):
            if _OUTLINE_NONE_RE.search(line) and not _FOCUS_RING_RE.search(line):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="outline-none without focus:ring replacement (WCAG 2.4.7)",
                        severity=self.severity,
                        file_path=context.file_path,
                        line=line_num,
                        suggestion="Add focus:ring-2 or focus-visible:ring-2 for keyboard users.",
                    )
                )

        return violations
