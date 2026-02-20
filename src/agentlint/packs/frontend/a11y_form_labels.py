"""Rule: form inputs without labels or aria-label (WCAG 1.3.1)."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.frontend._helpers import _WRITE_TOOLS, is_frontend_file

_FORM_ELEMENTS = {"input", "select", "textarea"}

# Types that don't need labels
_SKIP_TYPES = {"hidden", "submit", "button"}

# Attributes that satisfy labelling
_LABEL_ATTRS = {"aria-label", "aria-labelledby", "id"}

_FORM_TAG_RE = re.compile(r"<(input|select|textarea)\s([^>]*)/?>" , re.IGNORECASE)
_TYPE_RE = re.compile(r"""type\s*=\s*["'](\w+)["']""", re.IGNORECASE)


class A11yFormLabels(Rule):
    """Form inputs without labels or aria-label (WCAG 1.3.1)."""

    id = "a11y-form-labels"
    description = "Ensures form inputs have associated labels"
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

        has_label_tag = "<label" in content.lower()
        violations: list[Violation] = []

        for line_num, line in enumerate(content.splitlines(), start=1):
            for match in _FORM_TAG_RE.finditer(line):
                attrs = match.group(2)

                # Skip types that don't need labels
                type_match = _TYPE_RE.search(attrs)
                if type_match and type_match.group(1).lower() in _SKIP_TYPES:
                    continue

                # Check if any labelling attribute exists
                has_label_attr = any(attr in attrs for attr in ("aria-label", "aria-labelledby"))
                has_id = "id=" in attrs or "id =" in attrs

                if not has_label_attr and not (has_id and has_label_tag):
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=f"<{match.group(1)}> without label or aria-label (WCAG 1.3.1)",
                            severity=self.severity,
                            file_path=context.file_path,
                            line=line_num,
                            suggestion="Add aria-label, aria-labelledby, or an associated <label> element.",
                        )
                    )

        return violations
