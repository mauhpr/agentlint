"""Rule: warn about debug artifacts left in changed files."""
from __future__ import annotations

import re
from pathlib import Path

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_JS_EXTENSIONS = {".js", ".ts", ".tsx"}
_PY_EXTENSIONS = {".py"}

_CONSOLE_LOG_RE = re.compile(r"\bconsole\.log\(")
_DEBUGGER_RE = re.compile(r"\bdebugger\b")
_PRINT_RE = re.compile(r"\bprint\(")
_PDB_RE = re.compile(r"\bpdb\.set_trace\(\)")
_BREAKPOINT_RE = re.compile(r"\bbreakpoint\(\)")


def _is_test_file(path: str) -> bool:
    """Return True if the file path indicates a test file."""
    name = Path(path).name.lower()
    parts = Path(path).parts
    return "test" in name or any(p.lower() in ("tests", "test", "__tests__") for p in parts)


# Python files where print() is legitimate.
_PRINT_ALLOWED_NAMES = {"cli.py", "__main__.py", "manage.py", "setup.py"}


def _allows_print(path: str, content: str) -> bool:
    """Return True if print() is legitimate in this file."""
    name = Path(path).name.lower()
    if name in _PRINT_ALLOWED_NAMES:
        return True
    if 'if __name__' in content:
        return True
    return False


class NoDebugArtifacts(Rule):
    """Warn about debug artifacts left in changed files at session end."""

    id = "no-debug-artifacts"
    description = "Detects leftover debug statements (console.log, print, debugger, breakpoint)"
    severity = Severity.WARNING
    events = [HookEvent.STOP]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        changed_files: list[str] = context.session_state.get("changed_files", [])
        violations: list[Violation] = []

        for file_path in changed_files:
            if _is_test_file(file_path):
                continue

            path = Path(file_path)
            if not path.exists():
                continue

            suffix = path.suffix
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            artifacts: list[str] = []

            if suffix in _JS_EXTENSIONS:
                if _CONSOLE_LOG_RE.search(content):
                    artifacts.append("console.log()")
                if _DEBUGGER_RE.search(content):
                    artifacts.append("debugger")

            if suffix in _PY_EXTENSIONS:
                if _PRINT_RE.search(content) and not _allows_print(file_path, content):
                    artifacts.append("print()")
                if _PDB_RE.search(content):
                    artifacts.append("pdb.set_trace()")
                if _BREAKPOINT_RE.search(content):
                    artifacts.append("breakpoint()")

            if artifacts:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Debug artifacts in {file_path}: {', '.join(artifacts)}",
                        severity=self.severity,
                        file_path=file_path,
                        suggestion="Remove debug statements before finalizing.",
                    )
                )

        return violations
