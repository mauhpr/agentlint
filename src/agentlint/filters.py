"""Inline ignore directive filters for agentlint violations.

Supports three directive forms in source files:
- ``# agentlint:ignore-file`` — skip ALL rules for this file
- ``# agentlint:ignore <rule-id>`` — skip a specific rule for this file
- ``# agentlint:ignore-next-line`` — skip violations on the next line
"""
from __future__ import annotations

import re

from agentlint.models import Violation

_IGNORE_FILE_RE = re.compile(r"#\s*agentlint:ignore-file")
_IGNORE_RULE_RE = re.compile(r"#\s*agentlint:ignore\s+([\w-]+)")
_IGNORE_NEXT_RE = re.compile(r"#\s*agentlint:ignore-next-line")


def filter_inline_ignores(
    violations: list[Violation],
    file_content: str | None,
) -> list[Violation]:
    """Filter violations by inline ignore directives in file content.

    Returns a new list with suppressed violations removed.
    Violations without file_path or line numbers pass through unchanged
    (ignore-next-line only applies to violations with line numbers).
    """
    if not file_content or not violations:
        return violations

    # ignore-file: suppress everything
    if _IGNORE_FILE_RE.search(file_content):
        return []

    # Collect per-rule ignores
    ignored_rules: set[str] = set(_IGNORE_RULE_RE.findall(file_content))

    # Collect ignore-next-line → set of line numbers to suppress
    ignored_lines: set[int] = set()
    for i, line in enumerate(file_content.splitlines(), 1):
        if _IGNORE_NEXT_RE.search(line):
            ignored_lines.add(i + 1)

    return [
        v for v in violations
        if v.rule_id not in ignored_rules
        and (v.line is None or v.line not in ignored_lines)
    ]
