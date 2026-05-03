"""Output formatters for AgentLint.

Each formatter translates violations into a platform-specific output shape.
"""
from agentlint.formats.base import OutputFormatter
from agentlint.formats.claude_hooks import ClaudeHookFormatter
from agentlint.formats.cursor_hooks import CursorHookFormatter
from agentlint.formats.plain_json import PlainJsonFormatter

__all__ = [
    "ClaudeHookFormatter",
    "CursorHookFormatter",
    "OutputFormatter",
    "PlainJsonFormatter",
]
