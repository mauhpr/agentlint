"""Rule: warn when source files change without corresponding test changes."""
from __future__ import annotations

from pathlib import Path

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx"}

# File name patterns to skip (migrations, configs, etc.).
_SKIP_PATTERNS = ("migration", "alembic", "config", "settings", "conftest")


def _is_test_file(path: str) -> bool:
    """Return True if the path looks like a test file."""
    name = Path(path).name.lower()
    parts = Path(path).parts
    return "test" in name or any(p.lower() in ("tests", "test", "__tests__") for p in parts)


def _is_source_file(path: str) -> bool:
    """Return True if the path is a source file worth checking."""
    suffix = Path(path).suffix
    if suffix not in _SOURCE_EXTENSIONS:
        return False
    basename = Path(path).stem.lower()
    return not any(pattern in basename for pattern in _SKIP_PATTERNS)


class TestWithChanges(Rule):
    """Warn when source files change without corresponding test changes."""

    id = "test-with-changes"
    description = "Warns when source files are changed but no test files were updated"
    severity = Severity.WARNING
    events = [HookEvent.STOP]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        changed_files: list[str] = context.session_state.get("changed_files", [])
        if not changed_files:
            return []

        source_files = [f for f in changed_files if _is_source_file(f) and not _is_test_file(f)]
        test_files = [f for f in changed_files if _is_test_file(f)]

        if source_files and not test_files:
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Changed {len(source_files)} source file(s) but no test files were updated",
                    severity=self.severity,
                    suggestion="Consider adding or updating tests for the changed source files.",
                )
            ]

        return []
