"""Rule: interactive non-button elements without ARIA roles."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.frontend._helpers import _WRITE_TOOLS, is_frontend_file

_DEFAULT_ANTI_PATTERNS = {"click here", "read more", "learn more", "here"}

# div/span with onClick but missing role and tabIndex
_CLICKABLE_DIV_RE = re.compile(
    r"<(div|span)\s[^>]*onClick[^>]*>",
    re.IGNORECASE,
)

_ROLE_RE = re.compile(r"""\brole\s*=\s*["']""")
_TABINDEX_RE = re.compile(r"""\btabIndex\s*=""", re.IGNORECASE)

# Link anti-patterns
_LINK_RE = re.compile(r"<a\s[^>]*>([^<]*)</a>", re.IGNORECASE)


class A11yInteractiveElements(Rule):
    """Interactive non-button elements without ARIA roles."""

    id = "a11y-interactive-elements"
    description = "Ensures interactive elements have proper ARIA attributes"
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

        anti_patterns = set(context.config.get("link_anti_patterns", [])) or _DEFAULT_ANTI_PATTERNS
        violations: list[Violation] = []

        for line_num, line in enumerate(content.splitlines(), start=1):
            # Check div/span with onClick
            for match in _CLICKABLE_DIV_RE.finditer(line):
                tag_content = match.group(0)
                has_role = _ROLE_RE.search(tag_content)
                has_tabindex = _TABINDEX_RE.search(tag_content)
                if not has_role or not has_tabindex:
                    missing = []
                    if not has_role:
                        missing.append('role="button"')
                    if not has_tabindex:
                        missing.append("tabIndex")
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=f"<{match.group(1)}> with onClick missing {', '.join(missing)}",
                            severity=self.severity,
                            file_path=context.file_path,
                            line=line_num,
                            suggestion='Add role="button" and tabIndex={0} for keyboard accessibility.',
                        )
                    )

            # Check link anti-patterns
            for match in _LINK_RE.finditer(line):
                link_text = match.group(1).strip().lower()
                if link_text in anti_patterns:
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=f'Link with non-descriptive text: "{link_text}"',
                            severity=self.severity,
                            file_path=context.file_path,
                            line=line_num,
                            suggestion="Use descriptive link text that explains the destination.",
                        )
                    )

        return violations
