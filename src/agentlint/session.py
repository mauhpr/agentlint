"""Session state persistence for AgentLint.

Each Claude Code session gets a JSON file in ~/.cache/agentlint/sessions/
so that state survives across separate hook invocations (PreToolUse,
PostToolUse, Stop) within the same session.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

def _cache_dir() -> Path:
    """Return the cache directory, reading env var lazily."""
    return Path(os.environ.get("AGENTLINT_CACHE_DIR", "~/.cache/agentlint/sessions")).expanduser()


def _session_key() -> str:
    """Derive a session key from the environment."""
    return os.environ.get("CLAUDE_SESSION_ID", f"pid-{os.getppid()}")


def _session_path(key: str | None = None) -> Path:
    """Return the path for the session file."""
    key = key or _session_key()
    safe = key.replace("/", "_").replace("\\", "_")
    return _cache_dir() / f"{safe}.json"


def load_session(key: str | None = None) -> dict:
    """Load session state from disk; returns empty dict if missing."""
    path = _session_path(key)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_session(state: dict, key: str | None = None) -> None:
    """Persist session state to disk."""
    path = _session_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def cleanup_session(key: str | None = None) -> None:
    """Remove the session file (called on Stop)."""
    path = _session_path(key)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
