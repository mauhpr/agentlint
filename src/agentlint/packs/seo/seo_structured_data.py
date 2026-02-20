"""Rule: content pages without JSON-LD structured data."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.packs.seo._helpers import _WRITE_TOOLS

_SEO_EXTENSIONS = {".tsx", ".jsx", ".vue", ".svelte", ".html"}
_DEFAULT_CONTENT_PATTERNS = {"product", "article", "blog", "post", "recipe", "event"}

_JSONLD_RE = re.compile(r"application/ld\+json", re.IGNORECASE)


class SeoStructuredData(Rule):
    """Content pages without JSON-LD structured data."""

    id = "seo-structured-data"
    description = "Suggests adding JSON-LD structured data to content pages"
    severity = Severity.INFO
    events = [HookEvent.PRE_TOOL_USE]
    pack = "seo"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []

        file_path = context.file_path
        if not file_path:
            return []
        if not any(file_path.endswith(ext) for ext in _SEO_EXTENSIONS):
            return []

        content = context.tool_input.get("content", "")
        if not content:
            return []

        content_patterns = set(context.config.get("content_path_patterns", [])) or _DEFAULT_CONTENT_PATTERNS
        path_lower = file_path.lower()

        # Only check files whose path contains content-related keywords
        is_content_page = any(p in path_lower for p in content_patterns)
        if not is_content_page:
            return []

        if _JSONLD_RE.search(content):
            return []

        return [
            Violation(
                rule_id=self.id,
                message="Content page without JSON-LD structured data",
                severity=self.severity,
                file_path=file_path,
                suggestion='Add <script type="application/ld+json"> with appropriate schema.org data.',
            )
        ]
