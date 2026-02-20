"""Rule: arbitrary Tailwind values bypassing design tokens."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.frontend._helpers import _WRITE_TOOLS, is_frontend_file

# Hex colors in Tailwind: bg-[#...], text-[#...]
_HEX_COLOR_RE = re.compile(r"\b(?:bg|text|border|ring|fill|stroke)-\[#[0-9a-fA-F]+\]")

# Pixel spacing: p-[24px], m-[16px], gap-[8px]
_PIXEL_SPACING_RE = re.compile(r"\b(?:p|px|py|pt|pr|pb|pl|m|mx|my|mt|mr|mb|ml|gap|space-[xy])-\[\d+px\]")

# Layout arbitrary values (allowed by default)
_LAYOUT_ARBITRARY_RE = re.compile(r"\b(?:w|h|min-w|min-h|max-w|max-h|top|right|bottom|left|inset)-\[")


class StyleNoArbitraryValues(Rule):
    """Arbitrary Tailwind values bypassing design tokens."""

    id = "style-no-arbitrary-values"
    description = "Warns about arbitrary Tailwind values that bypass design tokens"
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

        violations: list[Violation] = []

        for line_num, line in enumerate(content.splitlines(), start=1):
            for match in _HEX_COLOR_RE.finditer(line):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Arbitrary hex color: {match.group()}",
                        severity=self.severity,
                        file_path=context.file_path,
                        line=line_num,
                        suggestion="Use a design token color (e.g., bg-primary, text-gray-500).",
                    )
                )

            for match in _PIXEL_SPACING_RE.finditer(line):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Arbitrary pixel spacing: {match.group()}",
                        severity=self.severity,
                        file_path=context.file_path,
                        line=line_num,
                        suggestion="Use Tailwind spacing scale (e.g., p-4, m-6, gap-2).",
                    )
                )

        return violations
