"""Inline ignore directive filters for agentlint violations.

Supports three directive forms in source files:
- ``# agentlint:ignore-file`` — skip ALL rules for this file
- ``# agentlint:ignore <rule-id>`` — skip a specific rule for this file
- ``# agentlint:ignore-next-line`` — skip violations on the next line

Per-rule ignores accept an optional ``reason="..."`` annotation
(``# agentlint:ignore my-rule reason="see issue #42"``) — reasons
surface in the session summary so suppressions are auditable rather
than anonymous. Reasons cannot contain the matching quote character;
escaped quotes inside the value are not supported (reasons are short).
"""
from __future__ import annotations

import re

from agentlint.models import Violation

_IGNORE_FILE_RE = re.compile(r"#\s*agentlint:ignore-file")
# Match ``# agentlint:ignore <rule-id>`` with an OPTIONAL trailing
# ``reason="..."`` or ``reason='...'`` annotation. The reason is
# captured as group 2 (or 3 when single quoted).
_IGNORE_RULE_RE = re.compile(
    r"#\s*agentlint:ignore\s+([\w-]+)"
    r"(?:\s+reason=(?:\"([^\"]*)\"|'([^']*)'))?"
)
_IGNORE_NEXT_RE = re.compile(r"#\s*agentlint:ignore-next-line")


def _parse_inline_ignores(
    file_content: str,
) -> tuple[set[str], dict[str, str | None]]:
    """Return ``(rule_ids, rule_id -> reason)`` from the file content.

    ``reason`` may be ``None`` when the user omitted the annotation.
    When the same rule is ignored multiple times with different reasons,
    the last reason wins — that matches "the closest comment to the
    violation site is the most relevant" intuition.
    """
    rule_ids: set[str] = set()
    reasons: dict[str, str | None] = {}
    for match in _IGNORE_RULE_RE.finditer(file_content):
        rid = match.group(1)
        # group 2 is double-quoted reason, group 3 is single-quoted
        reason = match.group(2) if match.group(2) is not None else match.group(3)
        rule_ids.add(rid)
        # Only overwrite an existing entry when we have a non-None reason
        # so a later bare ignore doesn't erase an earlier reason.
        if reason is not None or rid not in reasons:
            reasons[rid] = reason
    return rule_ids, reasons


def filter_inline_ignores(
    violations: list[Violation],
    file_content: str | None,
    file_path: str | None = None,
    session_state: dict | None = None,
) -> list[Violation]:
    """Filter violations by inline ignore directives in file content.

    Returns a new list with suppressed violations removed. Violations
    without file_path or line numbers pass through unchanged
    (``ignore-next-line`` only applies to violations with line numbers).

    When ``session_state`` is provided, every suppression is recorded in
    ``session_state["inline_ignores"]`` as
    ``{"file": ..., "rule_id": ..., "reason": ...}`` so the session
    summary can list overrides for auditability. ``file_path`` is used
    purely as the file label in those records.
    """
    if not file_content or not violations:
        return violations

    log = session_state.setdefault("inline_ignores", []) if session_state is not None else None

    def _record(rule_id: str, reason: str | None) -> None:
        if log is None:
            return
        log.append({
            "file": file_path,
            "rule_id": rule_id,
            "reason": reason,
        })

    # ignore-file: suppress everything. Record once per rule that fired
    # so the summary still shows what was overridden.
    if _IGNORE_FILE_RE.search(file_content):
        for v in violations:
            _record(v.rule_id, None)
        return []

    ignored_rules, reasons = _parse_inline_ignores(file_content)

    # Collect ignore-next-line → set of line numbers to suppress
    ignored_lines: set[int] = set()
    for i, line in enumerate(file_content.splitlines(), 1):
        if _IGNORE_NEXT_RE.search(line):
            ignored_lines.add(i + 1)

    kept: list[Violation] = []
    for v in violations:
        if v.rule_id in ignored_rules:
            _record(v.rule_id, reasons.get(v.rule_id))
            continue
        if v.line is not None and v.line in ignored_lines:
            _record(v.rule_id, None)
            continue
        kept.append(v)
    return kept
