"""Rule: warn when many files are edited without running tests."""
from __future__ import annotations

from pathlib import PurePosixPath

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}
_BASH_TOOLS = {"Bash"}

_TEST_RUNNERS = ("pytest", "vitest", "jest", "npm test", "make test")

_DEFAULT_THRESHOLD = 10

_DEFAULT_CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".rb",
    ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".cs", ".ex",
    ".vue", ".svelte",
}


class DriftDetector(Rule):
    """Warn when many files are edited without running tests."""

    id = "drift-detector"
    description = "Warns when many edits happen without running tests"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        state = context.session_state
        rule_config = context.config.get("drift-detector", {})
        threshold = rule_config.get("threshold", _DEFAULT_THRESHOLD)
        extensions = set(rule_config.get("extensions", list(_DEFAULT_CODE_EXTENSIONS)))

        # Track test runs from Bash commands.
        if context.tool_name in _BASH_TOOLS:
            command = context.command or ""
            if any(runner in command for runner in _TEST_RUNNERS):
                state["edited_files"] = []
                state["last_test_run"] = True
                return []

        # Track unique file edits — only count code files.
        if context.tool_name in _WRITE_TOOLS:
            edited = set(state.get("edited_files", []))
            file_path = context.file_path or context.tool_input.get("file_path", "")
            if file_path and PurePosixPath(file_path).suffix in extensions:
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
