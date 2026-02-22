"""Rule: warn when error handling patterns are removed from code."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_FILE_TOOLS = {"Write", "Edit"}

# Python error handling patterns
_PY_TRY_RE = re.compile(r"^\s*try\s*:", re.MULTILINE)
_PY_EXCEPT_RE = re.compile(r"^\s*except\b", re.MULTILINE)
_PY_NONE_CHECK_RE = re.compile(r"\bif\s+\w+\s+is\s+(?:not\s+)?None\b")

# JS/TS error handling patterns
_JS_TRY_RE = re.compile(r"\btry\s*\{", re.MULTILINE)
_JS_CATCH_RE = re.compile(r"\.catch\s*\(", re.MULTILINE)
_JS_ERROR_BOUNDARY_RE = re.compile(r"<ErrorBoundary\b", re.MULTILINE)

_TEST_PATTERNS = re.compile(r"test[_/]|spec[_/]|_test\.|\.test\.|\.spec\.", re.IGNORECASE)


def _count_error_handling(content: str, file_path: str) -> int:
    """Count error handling patterns in content."""
    count = 0
    if file_path.endswith(".py"):
        count += len(_PY_TRY_RE.findall(content))
        count += len(_PY_EXCEPT_RE.findall(content))
        count += len(_PY_NONE_CHECK_RE.findall(content))
    else:
        count += len(_JS_TRY_RE.findall(content))
        count += len(_JS_CATCH_RE.findall(content))
        count += len(_JS_ERROR_BOUNDARY_RE.findall(content))
    return count


def _is_code_file(path: str) -> bool:
    return any(
        path.endswith(ext)
        for ext in (".py", ".js", ".jsx", ".ts", ".tsx")
    )


class NoErrorHandlingRemoval(Rule):
    """Warn when error handling is removed from code."""

    id = "no-error-handling-removal"
    description = "Warns when error handling patterns (try/except, .catch) are removed"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "quality"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _FILE_TOOLS:
            return []

        file_path = context.file_path or ""
        if not file_path or not _is_code_file(file_path):
            return []

        # Skip test files
        if _TEST_PATTERNS.search(file_path):
            return []

        new_content = context.file_content or context.tool_input.get("content", "")
        if not new_content:
            return []

        old_content = context.file_content_before
        if not old_content:
            return []

        rule_config = context.config.get(self.id, {})
        if not rule_config.get("enabled", True):
            return []

        old_count = _count_error_handling(old_content, file_path)
        new_count = _count_error_handling(new_content, file_path)

        if old_count > 0 and new_count == 0:
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Error handling removed: {old_count} pattern(s) in previous version, 0 in new version",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Verify that error handling removal is intentional. Consider keeping try/except or .catch() blocks.",
                )
            ]

        return []
