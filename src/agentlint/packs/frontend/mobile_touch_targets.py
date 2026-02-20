"""Rule: interactive elements too small for touch (WCAG 2.5.5)."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.frontend._helpers import _WRITE_TOOLS, is_frontend_file

# Icon buttons with small Tailwind sizing classes
_SMALL_ICON_BUTTON_RE = re.compile(
    r"<button[^>]*class(?:Name)?\s*=\s*[\"'][^\"']*\b(?:w-[1-9]|h-[1-9]|p-[12])\b[^\"']*[\"'][^>]*>",
    re.IGNORECASE,
)

_MIN_SIZE_RE = re.compile(r"\bmin-[wh]-(?:1[1-9]|[2-9]\d)\b")


class MobileTouchTargets(Rule):
    """Interactive elements too small for touch (WCAG 2.5.5)."""

    id = "mobile-touch-targets"
    description = "Ensures interactive elements meet minimum touch target size"
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
            for match in _SMALL_ICON_BUTTON_RE.finditer(line):
                tag = match.group(0)
                if not _MIN_SIZE_RE.search(tag):
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message="Button may be too small for touch targets (44x44px minimum)",
                            severity=self.severity,
                            file_path=context.file_path,
                            line=line_num,
                            suggestion="Add min-w-11 min-h-11 (44px) for accessible touch targets.",
                        )
                    )

        return violations
