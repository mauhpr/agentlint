"""Agent platform adapters for AgentLint.

Each adapter translates a specific agent framework's events, tool names,
session identifiers, and output expectations into AgentLint's generic core.
"""
from __future__ import annotations

from agentlint.adapters.base import AgentAdapter

__all__ = [
    "AgentAdapter",
    "get_adapter",
]

# Registry mapping platform names to adapter classes.
# Lazy imports avoid pulling in heavy optional dependencies (fastmcp, etc.)
# unless the adapter is actually used.
_ADAPTER_REGISTRY: dict[str, str] = {
    "claude": "agentlint.adapters.claude.ClaudeAdapter",
    "cursor": "agentlint.adapters.cursor.CursorAdapter",
    "kimi": "agentlint.adapters.kimi.KimiAdapter",
    "grok": "agentlint.adapters.grok.GrokAdapter",
    "gemini": "agentlint.adapters.gemini.GeminiAdapter",
    "codex": "agentlint.adapters.codex.CodexAdapter",
    "continue": "agentlint.adapters.continue_dev.ContinueAdapter",
    "openai": "agentlint.adapters.openai_agents.OpenAIAgentsAdapter",
    "mcp": "agentlint.adapters.mcp.MCPAdapter",
    "generic": "agentlint.adapters.generic.GenericAdapter",
}


def get_adapter(name: str) -> AgentAdapter:
    """Return an adapter instance by platform name.

    Supported names: claude, cursor, kimi, grok, gemini, codex,
    continue, openai, mcp, generic.
    """
    if name not in _ADAPTER_REGISTRY:
        raise ValueError(f"Unknown adapter: {name!r}. Supported: {', '.join(_ADAPTER_REGISTRY)}")

    module_path, class_name = _ADAPTER_REGISTRY[name].rsplit(".", 1)
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()
