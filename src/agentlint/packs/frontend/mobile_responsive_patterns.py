"""Rule: desktop-only layout patterns."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.frontend._helpers import _WRITE_TOOLS, is_frontend_file

# grid-cols-{4-12} without responsive breakpoint
_GRID_COLS_RE = re.compile(r"\bgrid-cols-(\d+)\b")
_RESPONSIVE_GRID_RE = re.compile(r"\b(?:sm|md|lg|xl):grid-cols-")

# Fixed widths >= 400px
_FIXED_WIDTH_RE = re.compile(r"""\bw-\[(\d+)px\]""")

# Hover-only interactions
_HOVER_ONLY_RE = re.compile(r"\bonMouseEnter\b|\bonHover\b", re.IGNORECASE)
_CLICK_TOUCH_RE = re.compile(r"\bonClick\b|\bonTouchStart\b", re.IGNORECASE)


class MobileResponsivePatterns(Rule):
    """Desktop-only layout patterns."""

    id = "mobile-responsive-patterns"
    description = "Warns about desktop-only layout patterns"
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

        min_cols = context.config.get("min_grid_cols_warning", 4)
        violations: list[Violation] = []

        for line_num, line in enumerate(content.splitlines(), start=1):
            # Check for large grid without responsive breakpoint
            for match in _GRID_COLS_RE.finditer(line):
                cols = int(match.group(1))
                if cols >= min_cols and not _RESPONSIVE_GRID_RE.search(line):
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=f"grid-cols-{cols} without responsive breakpoint",
                            severity=self.severity,
                            file_path=context.file_path,
                            line=line_num,
                            suggestion=f"Add sm:grid-cols-2 md:grid-cols-{cols} for mobile.",
                        )
                    )

            # Check for fixed widths >= 400px
            for match in _FIXED_WIDTH_RE.finditer(line):
                width = int(match.group(1))
                if width >= 400:
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=f"Fixed width {width}px may cause horizontal scrolling on mobile",
                            severity=self.severity,
                            file_path=context.file_path,
                            line=line_num,
                            suggestion="Use max-w-* or responsive widths instead.",
                        )
                    )

            # Check hover-only interactions
            if _HOVER_ONLY_RE.search(line) and not _CLICK_TOUCH_RE.search(line):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="Hover-only interaction without click/touch fallback",
                        severity=self.severity,
                        file_path=context.file_path,
                        line=line_num,
                        suggestion="Add onClick or onTouchStart for mobile users.",
                    )
                )

        return violations
