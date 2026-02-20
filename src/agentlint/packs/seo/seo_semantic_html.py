"""Rule: pages with excessive divs and no semantic elements."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.seo._helpers import _WRITE_TOOLS, is_page_file

_DIV_RE = re.compile(r"<div\b", re.IGNORECASE)
_SEMANTIC_ELEMENTS = {"<main", "<article", "<section", "<nav", "<aside", "<header", "<footer"}


class SeoSemanticHtml(Rule):
    """Pages with excessive divs and no semantic elements."""

    id = "seo-semantic-html"
    description = "Encourages use of semantic HTML elements"
    severity = Severity.INFO
    events = [HookEvent.PRE_TOOL_USE]
    pack = "seo"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []

        file_path = context.file_path
        if not is_page_file(file_path):
            return []

        content = context.tool_input.get("content", "")
        if not content:
            return []

        min_divs = context.config.get("min_div_threshold", 10)
        content_lower = content.lower()

        div_count = len(_DIV_RE.findall(content_lower))
        if div_count < min_divs:
            return []

        has_semantic = any(elem in content_lower for elem in _SEMANTIC_ELEMENTS)
        if has_semantic:
            return []

        return [
            Violation(
                rule_id=self.id,
                message=f"{div_count} <div> elements and no semantic HTML elements",
                severity=self.severity,
                file_path=file_path,
                suggestion="Replace some <div> elements with <main>, <section>, <article>, <nav>.",
            )
        ]
