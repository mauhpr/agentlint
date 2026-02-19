"""Rule: warn when many files are edited without running tests."""
from __future__ import annotations

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}
_BASH_TOOLS = {"Bash"}

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
                state["edited_files"] = []
                state["last_test_run"] = True
                return []

        # Track unique file edits.
        if context.tool_name in _WRITE_TOOLS:
            edited = set(state.get("edited_files", []))
            file_path = context.file_path or context.tool_input.get("file_path", "")
            if file_path:
                edited.add(file_path)
            state["edited_files"] = list(edited)
            state["last_test_run"] = False

        files_edited = len(state.get("edited_files", []))
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
