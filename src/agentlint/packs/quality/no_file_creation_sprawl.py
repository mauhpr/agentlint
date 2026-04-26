"""Rule: warn when too many new files are created in a single session.

Encourages extending existing files rather than creating sprawl.
Tracks files created via session_state.

Files under common categories that legitimately proliferate (tests, docs,
migrations) are exempt by default so the counter reflects real source-file
sprawl rather than routine test/doc additions. Configure via the rule's
``exempt_paths`` key.
"""
from __future__ import annotations

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_DEFAULT_MAX_NEW_FILES = 10

# Path fragments whose presence in a created file's path means the file
# does not count toward the sprawl threshold. Matched as substrings so
# nested locations (e.g. ``backend/tests/foo_test.py``) work correctly.
_DEFAULT_EXEMPT_PATHS: tuple[str, ...] = (
    "tests/",
    "test/",
    "docs/",
    "alembic/versions/",
    "migrations/versions/",
    "spec/",
    "__tests__/",
)


def _is_exempt(file_path: str, exempt_paths: list[str]) -> bool:
    """Return True if file_path falls under any exempt path fragment."""
    normalised = file_path.replace("\\", "/")
    for fragment in exempt_paths:
        if fragment and fragment in normalised:
            return True
    return False


class NoFileCreationSprawl(Rule):
    id = "no-file-creation-sprawl"
    description = "Warns when too many new files are created in a session"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE]
    pack = "quality"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name != "Write":
            return []

        # Only trigger for new files (no file_content_before means it didn't exist)
        if context.file_content_before is not None:
            return []

        file_path = context.file_path
        if not file_path:
            return []

        rule_config = context.config.get(self.id, {})
        max_new = rule_config.get("max_new_files", _DEFAULT_MAX_NEW_FILES)
        # Defaults + user-supplied exemptions. The user list extends, not
        # replaces, the defaults so common cases stay covered.
        extra_exempt: list[str] = rule_config.get("exempt_paths", [])
        exempt_paths = list(_DEFAULT_EXEMPT_PATHS) + extra_exempt

        # Files in exempt categories never enter the counter. This means
        # later changing the config will not retroactively count earlier
        # files, but that's preferable to surprise re-fires mid-session.
        if _is_exempt(file_path, exempt_paths):
            return []

        # Track in session state
        created = context.session_state.setdefault("files_created", [])
        if file_path not in created:
            created.append(file_path)

        count = len(created)
        if count > max_new:
            return [Violation(
                rule_id=self.id,
                message=f"{count} new files created this session (max {max_new})",
                severity=self.severity,
                file_path=file_path,
                suggestion="Consider extending existing files instead of creating new ones",
            )]

        return []
