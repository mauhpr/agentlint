"""Rule: page files missing title/description metadata."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.seo._helpers import _WRITE_TOOLS, is_page_file

_DEFAULT_METADATA_MARKERS = {
    "<Head", "<Helmet", "<title", "generateMetadata", "metadata",
    "useHead", "useSeoMeta", "<svelte:head",
}


class SeoPageMetadata(Rule):
    """Page files missing title/description metadata."""

    id = "seo-page-metadata"
    description = "Ensures page files include title and description metadata"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "seo"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []

        file_path = context.file_path
        page_patterns = set(context.config.get("page_patterns", []))
        if not is_page_file(file_path, page_patterns or None):
            return []

        content = context.tool_input.get("content", "")
        if not content:
            return []

        extra_components = set(context.config.get("metadata_components", []))
        markers = _DEFAULT_METADATA_MARKERS | extra_components

        has_metadata = any(marker in content for marker in markers)
        if has_metadata:
            return []

        return [
            Violation(
                rule_id=self.id,
                message="Page file missing title/description metadata",
                severity=self.severity,
                file_path=file_path,
                suggestion="Add <Head>, <Helmet>, or generateMetadata for SEO.",
            )
        ]
