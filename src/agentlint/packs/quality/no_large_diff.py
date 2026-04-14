"""Rule: warn when a single Write/Edit produces a large diff.

Forces the agent to work in smaller, reviewable chunks. Uses
file_content_before (cached by PreToolUse) to compute diff size.

Test files and non-code files (.md, .yml, etc.) are exempt by default —
tests are inherently verbose, and config/prompt files are often large
single-write documents.
"""
from __future__ import annotations

import fnmatch
import os

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_DEFAULT_MAX_ADDED = 200
_DEFAULT_MAX_REMOVED = 100

_DEFAULT_TEST_PATTERNS = [
    "test_*",
    "*_test.*",
    "*.spec.*",
    "*.test.*",
    "*_spec.*",
    "conftest.py",
]

_DEFAULT_CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".rb",
    ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".cs", ".ex",
    ".vue", ".svelte",
}


def _is_test_file(file_path: str, patterns: list[str]) -> bool:
    """Check if file_path basename matches any test file pattern."""
    basename = os.path.basename(file_path)
    return any(fnmatch.fnmatch(basename, p) for p in patterns)


class NoLargeDiff(Rule):
    id = "no-large-diff"
    description = "Warns when a single edit adds or removes too many lines"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE]
    pack = "quality"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in ("Write", "Edit"):
            return []

        content_after = context.file_content
        content_before = context.file_content_before

        if content_after is None:
            return []

        rule_config = context.config.get(self.id, {})

        # Exempt non-code files — .md, .yml, .json, etc. are often large single-write documents
        if context.file_path:
            extensions = set(rule_config.get("extensions", list(_DEFAULT_CODE_EXTENSIONS)))
            ext = os.path.splitext(context.file_path)[1]
            if ext and ext not in extensions:
                return []

        # Exempt test files — comprehensive tests should not be penalized
        exempt_tests = rule_config.get("exempt_test_files", True)
        if exempt_tests and context.file_path:
            patterns = rule_config.get("test_file_patterns", _DEFAULT_TEST_PATTERNS)
            if _is_test_file(context.file_path, patterns):
                return []

        max_added = rule_config.get("max_lines_added", _DEFAULT_MAX_ADDED)
        max_removed = rule_config.get("max_lines_removed", _DEFAULT_MAX_REMOVED)

        lines_after = content_after.splitlines()
        lines_before = content_before.splitlines() if content_before else []

        added = max(0, len(lines_after) - len(lines_before))
        removed = max(0, len(lines_before) - len(lines_after))

        violations: list[Violation] = []

        if added > max_added:
            violations.append(Violation(
                rule_id=self.id,
                message=f"{added} lines added in a single edit (max {max_added})",
                severity=self.severity,
                file_path=context.file_path,
                suggestion="Break into smaller, reviewable changes",
            ))

        if removed > max_removed:
            violations.append(Violation(
                rule_id=self.id,
                message=f"{removed} lines removed in a single edit (max {max_removed})",
                severity=self.severity,
                file_path=context.file_path,
                suggestion="Review large deletions carefully before proceeding",
            ))

        return violations
