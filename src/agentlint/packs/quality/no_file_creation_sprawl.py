"""Rule: warn when too many new files are created in a single session.

Encourages extending existing files rather than creating sprawl.
Tracks files created via session_state.
"""
from __future__ import annotations

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_DEFAULT_MAX_NEW_FILES = 10


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
