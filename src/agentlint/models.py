"""Core models for AgentLint."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    """Rule violation severity levels."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def is_blocking(self) -> bool:
        return self == Severity.ERROR


class HookEvent(Enum):
    """Claude Code hook lifecycle events.

    Covers all 17 events supported by the Claude Code hook system.
    """
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    STOP = "Stop"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    SUB_AGENT_START = "SubagentStart"
    SUB_AGENT_STOP = "SubagentStop"
    NOTIFICATION = "Notification"
    PRE_COMPACT = "PreCompact"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    PERMISSION_REQUEST = "PermissionRequest"
    CONFIG_CHANGE = "ConfigChange"
    WORKTREE_CREATE = "WorktreeCreate"
    WORKTREE_REMOVE = "WorktreeRemove"
    TEAMMATE_IDLE = "TeammateIdle"
    TASK_COMPLETED = "TaskCompleted"

    @classmethod
    def from_string(cls, value: str) -> HookEvent:
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Unknown hook event: {value}")


@dataclass
class Violation:
    """A single rule violation."""
    rule_id: str
    message: str
    severity: Severity
    file_path: str | None = None
    line: int | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "message": self.message,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line": self.line,
            "suggestion": self.suggestion,
        }


@dataclass
class RuleContext:
    """Context passed to rules during evaluation."""
    event: HookEvent
    tool_name: str
    tool_input: dict
    project_dir: str
    file_content: str | None = None
    config: dict = field(default_factory=dict)
    session_state: dict = field(default_factory=dict)
    # v0.4.0 — additional context for new hook events
    prompt: str | None = None              # UserPromptSubmit
    subagent_output: str | None = None     # SubagentStop
    notification_type: str | None = None   # Notification
    compact_source: str | None = None      # PreCompact (manual/auto)
    file_content_before: str | None = None # PostToolUse diff support

    @property
    def file_path(self) -> str | None:
        return self.tool_input.get("file_path")

    @property
    def command(self) -> str | None:
        return self.tool_input.get("command")


class Rule(ABC):
    """Base class for all AgentLint rules."""
    id: str
    description: str
    severity: Severity
    events: list[HookEvent]
    pack: str

    @abstractmethod
    def evaluate(self, context: RuleContext) -> list[Violation]:
        """Evaluate this rule against the given context."""

    def matches_event(self, event: HookEvent) -> bool:
        """Check if this rule should run for the given event."""
        return event in self.events
