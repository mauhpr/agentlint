"""Rule: images without alt text (WCAG 1.1.1)."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.frontend._helpers import _WRITE_TOOLS, is_frontend_file

_DEFAULT_COMPONENTS = {"img", "Image"}

# Matches <img or <Image (or configured components) without alt= attribute
def _build_pattern(components: set[str]) -> re.Pattern:
    names = "|".join(re.escape(c) for c in sorted(components))
    return re.compile(
        r"<(?:" + names + r")\s+(?![^>]*\balt\s*=)[^>]*/?>",
        re.IGNORECASE,
    )


class A11yImageAlt(Rule):
    """Images without alt text (WCAG 1.1.1)."""

    id = "a11y-image-alt"
    description = "Ensures images have alt text for accessibility"
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

        extra = set(context.config.get("extra_components", []))
        components = _DEFAULT_COMPONENTS | extra
        pattern = _build_pattern(components)

        violations: list[Violation] = []
        for line_num, line in enumerate(content.splitlines(), start=1):
            for match in pattern.finditer(line):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="Image element missing alt attribute (WCAG 1.1.1)",
                        severity=self.severity,
                        file_path=context.file_path,
                        line=line_num,
                        suggestion='Add alt="descriptive text" or alt="" for decorative images.',
                    )
                )

        return violations
