"""Rule: heading structure issues."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.frontend._helpers import _WRITE_TOOLS, is_frontend_file

_HEADING_RE = re.compile(r"<h([1-6])\b", re.IGNORECASE)


class A11yHeadingHierarchy(Rule):
    """Heading structure issues — multiple h1 or skipped levels."""

    id = "a11y-heading-hierarchy"
    description = "Ensures proper heading hierarchy"
    severity = Severity.INFO
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

        max_h1 = context.config.get("max_h1", 1)
        violations: list[Violation] = []
        headings: list[tuple[int, int]] = []  # (level, line_num)

        for line_num, line in enumerate(content.splitlines(), start=1):
            for match in _HEADING_RE.finditer(line):
                level = int(match.group(1))
                headings.append((level, line_num))

        # Check multiple h1
        h1_lines = [ln for lvl, ln in headings if lvl == 1]
        if len(h1_lines) > max_h1:
            for ln in h1_lines[max_h1:]:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Multiple <h1> tags (max {max_h1})",
                        severity=self.severity,
                        file_path=context.file_path,
                        line=ln,
                        suggestion="Use only one <h1> per page for proper document outline.",
                    )
                )

        # Check skipped heading levels
        for i in range(1, len(headings)):
            prev_level = headings[i - 1][0]
            curr_level, curr_line = headings[i]
            if curr_level > prev_level + 1:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Skipped heading level: h{prev_level} to h{curr_level}",
                        severity=self.severity,
                        file_path=context.file_path,
                        line=curr_line,
                        suggestion=f"Add an <h{prev_level + 1}> between <h{prev_level}> and <h{curr_level}>.",
                    )
                )

        return violations
