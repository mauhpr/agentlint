"""Rule: block writing to .env files that may contain secrets."""
from __future__ import annotations

import os
import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}

# Patterns that are safe templates and should be allowed.
_SAFE_SUFFIXES = (".example", ".template", ".sample")

# .env filenames that should be blocked.
_BLOCKED_RE = re.compile(
    r"(^|/)\.env(\.local|\.production|\.staging|\.development)?$"
)


class NoEnvCommit(Rule):
    """Block writing to .env files that may contain real secrets."""

    id = "no-env-commit"
    description = "Prevents writing to .env files that may contain secrets"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []

        file_path: str | None = context.file_path
        if not file_path:
            return []

        basename = os.path.basename(file_path)

        # Allow safe template files.
        for suffix in _SAFE_SUFFIXES:
            if basename.endswith(suffix):
                return []

        if _BLOCKED_RE.search(file_path):
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Writing to env file is blocked: {file_path}",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Use .env.example for templates; keep real .env out of version control.",
                )
            ]

        return []
