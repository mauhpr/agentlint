"""Rule: warn when many files are edited without running tests.

Two firing channels (additive):

* **Mid-session warning** (POST_TOOL_USE): fires once when the agent has
  edited more than ``threshold`` code files since the last test run.
* **Commit-boundary warning** (PRE_TOOL_USE on a ``git commit``): fires
  once per commit attempt when the same condition holds. Resets when
  tests run successfully.

The mid-session warning is the existing v1.7+ behaviour. The commit
boundary warning was added in v1.10.0 in response to user feedback that
mid-session is the wrong moment for the nudge — at commit time the
agent is about to publish the work, which is the natural decision point.
"""
from __future__ import annotations

import re
from pathlib import PurePath

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}
_BASH_TOOLS = {"Bash"}

_TEST_RUNNERS = ("pytest", "vitest", "jest", "npm test", "make test")

# Match `git commit` but NOT `git commit --no-edit` or amend-no-edit which
# don't introduce new content. We're trying to catch the *content-publishing*
# event, not metadata-only commits.
_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")

_DEFAULT_THRESHOLD = 15

_DEFAULT_CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".rb",
    ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".cs", ".ex",
    ".vue", ".svelte",
}


def _is_metadata_only_commit(command: str) -> bool:
    """True for commits that don't publish new content (amend --no-edit)."""
    return "--no-edit" in command


class DriftDetector(Rule):
    """Warn when many files are edited without running tests."""

    id = "drift-detector"
    description = "Warns when many edits happen without running tests"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        state = context.session_state
        rule_config = context.config.get("drift-detector", {})
        threshold = rule_config.get("threshold", _DEFAULT_THRESHOLD)
        extensions = set(rule_config.get("extensions", list(_DEFAULT_CODE_EXTENSIONS)))

        # PRE_TOOL_USE: only fire on `git commit` (commit-boundary nudge).
        if context.event == HookEvent.PRE_TOOL_USE:
            if context.tool_name not in _BASH_TOOLS:
                return []
            command = context.command or ""
            if not _GIT_COMMIT_RE.search(command):
                return []
            if _is_metadata_only_commit(command):
                return []

            files_edited = len(state.get("edited_files", []))
            last_test_run = state.get("last_test_run", True)

            if files_edited > threshold and not last_test_run:
                if state.get("_drift_warned_at_commit"):
                    return []
                state["_drift_warned_at_commit"] = True
                return [
                    Violation(
                        rule_id=self.id,
                        message=(
                            f"Committing {files_edited} edits without running tests "
                            "since last test run"
                        ),
                        severity=self.severity,
                        suggestion=(
                            "Run your test suite before committing — drift this large "
                            "is a common source of regressions."
                        ),
                    )
                ]
            return []

        # POST_TOOL_USE: existing mid-session behaviour, unchanged.
        # Track test runs from Bash commands.
        if context.tool_name in _BASH_TOOLS:
            command = context.command or ""
            if any(runner in command for runner in _TEST_RUNNERS):
                state["edited_files"] = []
                state["last_test_run"] = True
                state["_drift_warned"] = False
                state["_drift_warned_at_commit"] = False
                return []

        # Track unique file edits — only count code files.
        if context.tool_name in _WRITE_TOOLS:
            edited = set(state.get("edited_files", []))
            file_path = context.file_path or context.tool_input.get("file_path", "")
            if file_path and PurePath(file_path).suffix in extensions:
                edited.add(file_path)
            state["edited_files"] = list(edited)
            state["last_test_run"] = False

        files_edited = len(state.get("edited_files", []))
        last_test_run = state.get("last_test_run", True)

        if files_edited > threshold and not last_test_run:
            # Fire once when threshold is crossed, not on every subsequent edit
            if state.get("_drift_warned"):
                return []
            state["_drift_warned"] = True
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Edited {files_edited} files without running tests",
                    severity=self.severity,
                    suggestion="Consider running your test suite to catch regressions early.",
                )
            ]

        return []
