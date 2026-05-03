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


class AgentEvent(Enum):
    """Generic agent lifecycle events.

    Normalized taxonomy that abstracts across Claude Code, Cursor, OpenAI
    Agents SDK, MCP hosts, and custom agent frameworks.
    """
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    POST_TOOL_FAILURE = "post_tool_failure"
    USER_PROMPT = "user_prompt"
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    SUB_AGENT_START = "sub_agent_start"
    SUB_AGENT_STOP = "sub_agent_stop"
    NOTIFICATION = "notification"
    PRE_COMPACT = "pre_compact"
    PERMISSION_REQUEST = "permission_request"
    CONFIG_CHANGE = "config_change"
    WORKTREE_CREATE = "worktree_create"
    WORKTREE_REMOVE = "worktree_remove"
    TEAMMATE_IDLE = "teammate_idle"
    TASK_COMPLETED = "task_completed"
    STOP = "stop"

    @classmethod
    def from_string(cls, value: str) -> AgentEvent:
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Unknown agent event: {value}")


class HookEvent(Enum):
    """Hook lifecycle events.

    These are the canonical event names used by AgentLint's rule engine.
    For backward compatibility, the string values match the original
    Claude Code hook event names. New code should prefer AgentEvent.
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


# Mapping between generic AgentEvent and legacy HookEvent
_AGENT_EVENT_TO_HOOK_EVENT: dict[AgentEvent, HookEvent] = {
    AgentEvent.PRE_TOOL_USE: HookEvent.PRE_TOOL_USE,
    AgentEvent.POST_TOOL_USE: HookEvent.POST_TOOL_USE,
    AgentEvent.POST_TOOL_FAILURE: HookEvent.POST_TOOL_USE_FAILURE,
    AgentEvent.USER_PROMPT: HookEvent.USER_PROMPT_SUBMIT,
    AgentEvent.SESSION_START: HookEvent.SESSION_START,
    AgentEvent.SESSION_END: HookEvent.SESSION_END,
    AgentEvent.SUB_AGENT_START: HookEvent.SUB_AGENT_START,
    AgentEvent.SUB_AGENT_STOP: HookEvent.SUB_AGENT_STOP,
    AgentEvent.NOTIFICATION: HookEvent.NOTIFICATION,
    AgentEvent.PRE_COMPACT: HookEvent.PRE_COMPACT,
    AgentEvent.PERMISSION_REQUEST: HookEvent.PERMISSION_REQUEST,
    AgentEvent.CONFIG_CHANGE: HookEvent.CONFIG_CHANGE,
    AgentEvent.WORKTREE_CREATE: HookEvent.WORKTREE_CREATE,
    AgentEvent.WORKTREE_REMOVE: HookEvent.WORKTREE_REMOVE,
    AgentEvent.TEAMMATE_IDLE: HookEvent.TEAMMATE_IDLE,
    AgentEvent.TASK_COMPLETED: HookEvent.TASK_COMPLETED,
    AgentEvent.STOP: HookEvent.STOP,
}

_HOOK_EVENT_TO_AGENT_EVENT: dict[HookEvent, AgentEvent] = {
    v: k for k, v in _AGENT_EVENT_TO_HOOK_EVENT.items()
}


def to_hook_event(event: AgentEvent | HookEvent | str) -> HookEvent:
    """Convert an AgentEvent or string to its HookEvent equivalent."""
    if isinstance(event, HookEvent):
        return event
    if isinstance(event, str):
        try:
            return HookEvent.from_string(event)
        except ValueError:
            pass
        try:
            return _AGENT_EVENT_TO_HOOK_EVENT[AgentEvent.from_string(event)]
        except ValueError:
            pass
        raise ValueError(f"No HookEvent mapping for string: {event}")
    try:
        return _AGENT_EVENT_TO_HOOK_EVENT[event]
    except KeyError:
        raise ValueError(f"No HookEvent mapping for {event}")


def to_agent_event(event: HookEvent | AgentEvent) -> AgentEvent:
    """Convert a HookEvent to its AgentEvent equivalent."""
    if isinstance(event, AgentEvent):
        return event
    try:
        return _HOOK_EVENT_TO_AGENT_EVENT[event]
    except KeyError:
        raise ValueError(f"No AgentEvent mapping for {event}")


class NormalizedTool(Enum):
    """Normalized tool taxonomy across agent platforms.

    Adapters map vendor-specific tool names to this taxonomy so that
    rules can be written once and work everywhere.
    """
    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"
    SHELL = "shell"
    FILE_READ = "file_read"
    SEARCH = "search"
    WEB_FETCH = "web_fetch"
    WEB_SEARCH = "web_search"
    SUB_AGENT = "sub_agent"
    NOTEBOOK = "notebook"
    UNKNOWN = "unknown"


# Claude Code tool name mappings
_CLAUDE_TOOL_MAP: dict[str, NormalizedTool] = {
    "Write": NormalizedTool.FILE_WRITE,
    "Edit": NormalizedTool.FILE_EDIT,
    "Bash": NormalizedTool.SHELL,
    "Read": NormalizedTool.FILE_READ,
    "Glob": NormalizedTool.SEARCH,
    "Grep": NormalizedTool.SEARCH,
    "Agent": NormalizedTool.SUB_AGENT,
    "Task": NormalizedTool.SUB_AGENT,
    "WebFetch": NormalizedTool.WEB_FETCH,
    "WebSearch": NormalizedTool.WEB_SEARCH,
    "NotebookEdit": NormalizedTool.NOTEBOOK,
    "MultiEdit": NormalizedTool.FILE_EDIT,
}

# Kimi tool name mappings
_KIMI_TOOL_MAP: dict[str, NormalizedTool] = {
    "Shell": NormalizedTool.SHELL,
    "WriteFile": NormalizedTool.FILE_WRITE,
    "StrReplaceFile": NormalizedTool.FILE_EDIT,
    "ReadFile": NormalizedTool.FILE_READ,
    "Grep": NormalizedTool.SEARCH,
    "Glob": NormalizedTool.SEARCH,
    "Task": NormalizedTool.SUB_AGENT,
    "Agent": NormalizedTool.SUB_AGENT,
    "WebFetch": NormalizedTool.WEB_FETCH,
    "WebSearch": NormalizedTool.WEB_SEARCH,
}

# Grok tool name mappings
_GROK_TOOL_MAP: dict[str, NormalizedTool] = {
    "bash": NormalizedTool.SHELL,
    "write": NormalizedTool.FILE_WRITE,
    "edit": NormalizedTool.FILE_EDIT,
    "read": NormalizedTool.FILE_READ,
    "grep": NormalizedTool.SEARCH,
    "glob": NormalizedTool.SEARCH,
    "task": NormalizedTool.SUB_AGENT,
    "delegate": NormalizedTool.SUB_AGENT,
    "web_fetch": NormalizedTool.WEB_FETCH,
    "web_search": NormalizedTool.WEB_SEARCH,
    "search_x": NormalizedTool.WEB_SEARCH,
    "search_web": NormalizedTool.WEB_SEARCH,
    "generate_image": NormalizedTool.NOTEBOOK,
    "generate_video": NormalizedTool.NOTEBOOK,
}

# Gemini tool name mappings
_GEMINI_TOOL_MAP: dict[str, NormalizedTool] = {
    "bash": NormalizedTool.SHELL,
    "write_file": NormalizedTool.FILE_WRITE,
    "replace": NormalizedTool.FILE_EDIT,
    "read_file": NormalizedTool.FILE_READ,
    "grep": NormalizedTool.SEARCH,
    "glob": NormalizedTool.SEARCH,
    "web_search": NormalizedTool.WEB_SEARCH,
    "web_fetch": NormalizedTool.WEB_FETCH,
}

# Codex tool name mappings
_CODEX_TOOL_MAP: dict[str, NormalizedTool] = {
    "Bash": NormalizedTool.SHELL,
    "apply_patch": NormalizedTool.FILE_EDIT,
    "Read": NormalizedTool.FILE_READ,
    "WebSearch": NormalizedTool.WEB_SEARCH,
    "WebFetch": NormalizedTool.WEB_FETCH,
}

# Continue.dev tool name mappings (same as Claude)
_CONTINUE_TOOL_MAP: dict[str, NormalizedTool] = dict(_CLAUDE_TOOL_MAP)

# Platform → tool map registry
_PLATFORM_TOOL_MAPS: dict[str, dict[str, NormalizedTool]] = {
    "claude": _CLAUDE_TOOL_MAP,
    "kimi": _KIMI_TOOL_MAP,
    "grok": _GROK_TOOL_MAP,
    "gemini": _GEMINI_TOOL_MAP,
    "codex": _CODEX_TOOL_MAP,
    "continue": _CONTINUE_TOOL_MAP,
}


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
    # v0.8.0 — subagent context fields
    agent_transcript_path: str | None = None  # SubagentStop — path to JSONL transcript
    agent_type: str | None = None             # SubagentStart/SubagentStop — agent type name
    agent_id: str | None = None               # SubagentStart/SubagentStop — unique ID
    # v2.0.0 — agent-agnostic platform identification
    agent_platform: str = "unknown"           # "claude", "cursor", "openai", "mcp", etc.

    @property
    def file_path(self) -> str | None:
        return self.tool_input.get("file_path")

    @property
    def command(self) -> str | None:
        return self.tool_input.get("command")

    @property
    def normalized_tool(self) -> NormalizedTool:
        """Return the normalized tool type for this context.

        Falls back to UNKNOWN if the agent platform is not recognized
        or the tool name has no mapping.
        """
        tool_map = _PLATFORM_TOOL_MAPS.get(self.agent_platform, _CLAUDE_TOOL_MAP)
        return tool_map.get(self.tool_name, NormalizedTool.UNKNOWN)


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

    def matches_event(self, event: HookEvent | AgentEvent) -> bool:
        """Check if this rule should run for the given event.

        Accepts both HookEvent (legacy) and AgentEvent (generic) for
        backward compatibility during the v2 migration.
        """
        hook_event = to_hook_event(event) if isinstance(event, AgentEvent) else event
        return hook_event in self.events
