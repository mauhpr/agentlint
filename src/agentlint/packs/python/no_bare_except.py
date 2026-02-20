"""Rule: detect bare except: clauses that swallow all exceptions."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}

_BARE_EXCEPT_RE = re.compile(r"^\s*except\s*:", re.MULTILINE)


class NoBareExcept(Rule):
    """Detect bare except: that swallows SystemExit/KeyboardInterrupt."""

    id = "no-bare-except"
    description = "Prevents bare except: clauses that catch all exceptions"
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

        allow_reraise = context.config.get("allow_reraise", True)
        violations: list[Violation] = []
        lines = content.splitlines()

        for i, line in enumerate(lines):
            if not _BARE_EXCEPT_RE.match(line):
                continue

            # Check if the except block contains a bare raise (reraise)
            if allow_reraise:
                indent = len(line) - len(line.lstrip())
                has_raise = False
                for subsequent in lines[i + 1 :]:
                    stripped = subsequent.lstrip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    sub_indent = len(subsequent) - len(subsequent.lstrip())
                    if sub_indent <= indent and stripped:
                        break
                    if stripped == "raise" or stripped.startswith("raise "):
                        has_raise = True
                        break
                if has_raise:
                    continue

            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Bare except: catches SystemExit and KeyboardInterrupt",
                    severity=self.severity,
                    file_path=file_path,
                    line=i + 1,
                    suggestion="Use 'except Exception:' instead of bare 'except:'.",
                )
            )

        return violations
