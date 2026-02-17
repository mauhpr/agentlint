"""Rule: warn when many files are edited without running tests."""
from __future__ import annotations

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit", "write", "edit"}
_BASH_TOOLS = {"Bash", "bash"}

_TEST_RUNNERS = ("pytest", "vitest", "jest", "npm test", "make test")

_DEFAULT_THRESHOLD = 10


class DriftDetector(Rule):
    """Warn when many files are edited without running tests."""

    id = "drift-detector"
    description = "Warns when many edits happen without running tests"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        state = context.session_state
        threshold = context.config.get("drift-detector", {}).get("threshold", _DEFAULT_THRESHOLD)

        # Track test runs from Bash commands.
        if context.tool_name in _BASH_TOOLS:
            command = context.command or ""
            if any(runner in command for runner in _TEST_RUNNERS):
                state["files_edited"] = 0
                state["last_test_run"] = True
                return []

        # Track file edits.
        if context.tool_name in _WRITE_TOOLS:
            state["files_edited"] = state.get("files_edited", 0) + 1
            state["last_test_run"] = False

        files_edited = state.get("files_edited", 0)
        last_test_run = state.get("last_test_run", True)

        if files_edited > threshold and not last_test_run:
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Edited {files_edited} files without running tests",
                    severity=self.severity,
                    suggestion="Consider running your test suite to catch regressions early.",
                )
            ]

        return []
