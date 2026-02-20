"""Rule: detect unsafe shell execution in Python code."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}

# Detects os.system() and os.popen() calls
_OS_SHELL_RE = re.compile(r"\bos\.(system|popen)\s*\(")

# subprocess with shell=True and a string argument
_SUBPROCESS_SHELL_RE = re.compile(
    r"\bsubprocess\.(call|run|Popen)\s*\([^)]*shell\s*=\s*True",
    re.DOTALL,
)


class NoUnsafeShell(Rule):
    """Detect unsafe shell execution in Python code being written."""

    id = "no-unsafe-shell"
    description = "Prevents unsafe shell execution via subprocess with shell=True"
    severity = Severity.ERROR
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

        allow_shell_true = context.config.get("allow_shell_true", False)
        violations: list[Violation] = []

        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue

            if _OS_SHELL_RE.search(line):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="Unsafe shell execution detected",
                        severity=self.severity,
                        file_path=file_path,
                        line=line_num,
                        suggestion="Use subprocess.run() with a list of arguments instead.",
                    )
                )

        # Check for subprocess with shell=True across the full content
        if not allow_shell_true:
            for match in _SUBPROCESS_SHELL_RE.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Unsafe shell execution: subprocess.{match.group(1)}() with shell=True",
                        severity=self.severity,
                        file_path=file_path,
                        line=line_num,
                        suggestion="Pass a list of arguments instead of a shell string.",
                    )
                )

        return violations
