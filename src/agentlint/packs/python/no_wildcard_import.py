"""Rule: detect wildcard imports (from module import *)."""
from __future__ import annotations

import os
import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}

_WILDCARD_IMPORT_RE = re.compile(r"^\s*from\s+\S+\s+import\s+\*", re.MULTILINE)


class NoWildcardImport(Rule):
    """Detect from module import * statements."""

    id = "no-wildcard-import"
    description = "Prevents wildcard imports that pollute the namespace"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "python"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []

        file_path = context.file_path
        if not file_path or not file_path.endswith(".py"):
            return []

        content = context.tool_input.get("content", "")
        if not content:
            return []

        allow_in = context.config.get("allow_in", ["__init__.py"])
        basename = os.path.basename(file_path)
        if basename in allow_in:
            return []

        violations: list[Violation] = []
        for line_num, line in enumerate(content.splitlines(), start=1):
            if _WILDCARD_IMPORT_RE.match(line):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="Wildcard import (from ... import *) pollutes namespace",
                        severity=self.severity,
                        file_path=file_path,
                        line=line_num,
                        suggestion="Import specific names instead of using import *.",
                    )
                )

        return violations
