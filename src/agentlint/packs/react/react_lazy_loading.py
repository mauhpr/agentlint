"""Rule: heavy components imported at top level in page files."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}
_REACT_EXTENSIONS = {".tsx", ".jsx"}

_DEFAULT_HEAVY_COMPONENTS = {
    "Chart", "DataTable", "Editor", "Calendar", "Map",
    "RichTextEditor", "CodeEditor", "Spreadsheet",
}

_DEFAULT_PAGE_PATTERNS = {"pages/", "app/", "routes/"}

_LAZY_RE = re.compile(r"\bReact\.lazy\b|\blazy\s*\(")
_SUSPENSE_RE = re.compile(r"<Suspense\b")


def _is_react_file(file_path: str | None) -> bool:
    if not file_path:
        return False
    return any(file_path.endswith(ext) for ext in _REACT_EXTENSIONS)


def _is_page_file(file_path: str, page_patterns: set[str]) -> bool:
    return any(p in file_path for p in page_patterns)


class ReactLazyLoading(Rule):
    """Heavy components imported at top level in page files."""

    id = "react-lazy-loading"
    description = "Suggests lazy loading for heavy components in page files"
    severity = Severity.INFO
    events = [HookEvent.PRE_TOOL_USE]
    pack = "react"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []
        if not _is_react_file(context.file_path):
            return []

        content = context.tool_input.get("content", "")
        if not content:
            return []

        file_path = context.file_path or ""
        heavy = set(context.config.get("heavy_components", [])) or _DEFAULT_HEAVY_COMPONENTS
        page_patterns = set(context.config.get("page_patterns", [])) or _DEFAULT_PAGE_PATTERNS

        violations: list[Violation] = []

        # Check 1: Regular import of heavy components in page files
        if _is_page_file(file_path, page_patterns):
            for component in heavy:
                import_re = re.compile(
                    r"^import\s+.*\b" + re.escape(component) + r"\b",
                    re.MULTILINE,
                )
                for match in import_re.finditer(content):
                    line_num = content[:match.start()].count("\n") + 1
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=f"Heavy component '{component}' imported at top level in page file",
                            severity=self.severity,
                            file_path=context.file_path,
                            line=line_num,
                            suggestion=f"Use React.lazy(() => import('.../{component}')) with <Suspense>.",
                        )
                    )

        # Check 2: React.lazy() without <Suspense>
        if _LAZY_RE.search(content) and not _SUSPENSE_RE.search(content):
            for match in _LAZY_RE.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="React.lazy() without <Suspense> fallback",
                        severity=self.severity,
                        file_path=context.file_path,
                        line=line_num,
                        suggestion="Wrap lazy-loaded components in <Suspense fallback={...}>.",
                    )
                )

        return violations
