"""Rule: inform about TODO/FIXME/HACK/XXX comments left in changed files."""
from __future__ import annotations

import re
from pathlib import Path

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

# Match TODO, FIXME, HACK, XXX preceded by a comment marker (#, //, or /*).
_TODO_RE = re.compile(r"(?:#|//|/\*)\s*(?:TODO|FIXME|HACK|XXX)\b")


class NoTodoLeft(Rule):
    """Inform about TODO/FIXME/HACK/XXX comments left in changed files."""

    id = "no-todo-left"
    description = "Detects leftover TODO/FIXME/HACK/XXX comments in changed files"
    severity = Severity.INFO
    events = [HookEvent.STOP]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        changed_files: list[str] = context.session_state.get("changed_files", [])
        violations: list[Violation] = []

        for file_path in changed_files:
            path = Path(file_path)
            if not path.exists():
                continue

            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            matches = _TODO_RE.findall(content)
            if matches:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Found {len(matches)} TODO/FIXME comment(s) in {file_path}",
                        severity=self.severity,
                        file_path=file_path,
                        suggestion="Review and resolve TODO comments before finalizing.",
                    )
                )

        return violations
