"""Rule: array .map() without empty state handling."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}
_REACT_EXTENSIONS = {".tsx", ".jsx"}

# Detects .map( in JSX context (inside return/render)
_MAP_RE = re.compile(r"\.map\s*\(")
_LENGTH_CHECK_RE = re.compile(r"\.length\b")
_GUARD_RE = re.compile(r"&&\s*\w+\.map|\.length\s*[>!=]|\?\s*\w+\.map|\bif\s*\([^)]*\.length")


def _is_react_file(file_path: str | None) -> bool:
    if not file_path:
        return False
    return any(file_path.endswith(ext) for ext in _REACT_EXTENSIONS)


class ReactEmptyState(Rule):
    """Array .map() without empty state handling."""

    id = "react-empty-state"
    description = "Suggests adding empty state handling for array.map() in JSX"
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

        # If there's a length check anywhere, assume it's handled
        if _GUARD_RE.search(content):
            return []

        violations: list[Violation] = []
        for match in _MAP_RE.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            # Check surrounding context for length check
            start = max(0, match.start() - 200)
            end = min(len(content), match.end() + 200)
            context_window = content[start:end]
            if _LENGTH_CHECK_RE.search(context_window):
                continue

            violations.append(
                Violation(
                    rule_id=self.id,
                    message=".map() without empty state handling",
                    severity=self.severity,
                    file_path=context.file_path,
                    line=line_num,
                    suggestion="Add a .length check or empty state component for when the array is empty.",
                )
            )

        return violations
