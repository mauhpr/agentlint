"""Rule: pages with metadata but missing OG tags."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.seo._helpers import _WRITE_TOOLS, is_page_file

_METADATA_MARKERS = {"<Head", "<Helmet", "<title", "generateMetadata", "metadata"}
_DEFAULT_REQUIRED = {"og:title", "og:description", "og:image"}


class SeoOpenGraph(Rule):
    """Pages with metadata but missing OG tags."""

    id = "seo-open-graph"
    description = "Ensures pages with metadata also include Open Graph tags"
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

        # Only check files that already have some metadata
        has_metadata = any(marker in content for marker in _METADATA_MARKERS)
        if not has_metadata:
            return []

        required = set(context.config.get("required_properties", [])) or _DEFAULT_REQUIRED
        missing = [prop for prop in sorted(required) if prop not in content]

        if not missing:
            return []

        return [
            Violation(
                rule_id=self.id,
                message=f"Missing Open Graph tags: {', '.join(missing)}",
                severity=self.severity,
                file_path=file_path,
                suggestion="Add og:title, og:description, and og:image meta tags.",
            )
        ]
