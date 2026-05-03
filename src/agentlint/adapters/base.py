"""Base adapter protocol for agent platform integration."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from agentlint.formats.base import OutputFormatter
from agentlint.models import AgentEvent, RuleContext


class AgentAdapter(ABC):
    """Abstract base for platform-specific agent adapters.

    An adapter bridges one agent framework (Claude Code, Cursor, OpenAI
    Agents, MCP, etc.) to AgentLint's generic core. It is responsible for:

    1. Event translation — converting native events to AgentEvent
    2. Tool normalization — mapping vendor tool names to NormalizedTool
    3. Session identification — deriving a stable session key
    4. Output formatting — producing responses the agent understands
    5. Installation — writing hook/config files the agent loads
    """

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Human-readable platform name, e.g. 'claude', 'cursor', 'openai'."""

    @property
    @abstractmethod
    def formatter(self) -> OutputFormatter:
        """Return the output formatter for this platform."""

    @abstractmethod
    def resolve_project_dir(self) -> str:
        """Determine the project directory from environment or cwd."""

    @abstractmethod
    def resolve_session_key(self) -> str:
        """Derive a stable session key for the current agent session."""

    @abstractmethod
    def translate_event(self, native_event: str) -> AgentEvent:
        """Convert a native event name to the generic AgentEvent taxonomy."""

    @abstractmethod
    def normalize_tool_name(self, native_tool: str) -> str:
        """Map a vendor-specific tool name to a normalized identifier."""

    @abstractmethod
    def build_rule_context(
        self,
        event: AgentEvent,
        raw_payload: dict[str, Any],
        project_dir: str,
        session_state: dict,
    ) -> RuleContext:
        """Construct a RuleContext from the agent's native payload."""

    @abstractmethod
    def install_hooks(
        self,
        project_dir: str,
        scope: str = "project",
        dry_run: bool = False,
        cmd: str | None = None,
    ) -> None:
        """Install AgentLint hooks into the agent's configuration."""

    @abstractmethod
    def uninstall_hooks(
        self,
        project_dir: str,
        scope: str = "project",
    ) -> None:
        """Remove AgentLint hooks from the agent's configuration."""
