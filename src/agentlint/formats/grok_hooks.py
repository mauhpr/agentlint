"""Grok's native advisory context lives at the top level."""

from __future__ import annotations

import json

from agentlint.formats.claude_hooks import ClaudeHookFormatter
from agentlint.models import AgentEvent


class GrokHookFormatter(ClaudeHookFormatter):
    def add_activity_context(self, output: str | None, event: AgentEvent, message: str) -> str:
        payload = json.loads(output) if output else {}
        payload["additionalContext"] = "\n".join(
            filter(None, [payload.get("additionalContext"), message])
        )
        return json.dumps(payload)
