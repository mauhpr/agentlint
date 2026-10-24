"""Rule: warn when a file exceeds a configurable line-count limit."""

from __future__ import annotations

import json
from pathlib import PurePath

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}

_DEFAULT_LIMIT = 500


class MaxFileSize(Rule):
    """Warn when a written/edited file exceeds a line-count threshold."""

    id = "max-file-size"
    description = "Warns before Write/Edit exceeds a line-count limit, with post-write fallback"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []

        content = context.file_content
        if content is None:
            return []

        # JSON is structured data: pretty-printing a receipt must not turn it
        # into an oversized code module. Other rules still inspect its content.
        rule_config = context.config.get(self.id, {})
        if (
            rule_config.get("exempt_json_data", True)
            and PurePath(context.file_path or "").suffix.lower() == ".json"
        ):
            try:
                json.loads(content)
            except (ValueError, RecursionError):
                pass
            else:
                return []

        limit = rule_config.get("limit", _DEFAULT_LIMIT)
        line_count = content.count("\n") + (1 if content and not content.endswith("\n") else 0)

        if line_count > limit:
            # Don't fire on pre-existing large files — only when crossing the threshold
            before = context.file_content_before
            if before is not None:
                before_count = before.count("\n") + (
                    1 if before and not before.endswith("\n") else 0
                )
                if before_count > limit:
                    return []  # file was already over the limit before this edit

            over = line_count - limit
            return [
                Violation(
                    rule_id=self.id,
                    message=f"File has {line_count} lines (limit: {limit}, +{over} over)",
                    severity=self.severity,
                    file_path=context.file_path,
                    suggestion=f"Remove {over} line{'s' if over != 1 else ''} or split into smaller modules.",
                )
            ]

        return []
