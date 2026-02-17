"""Hook installation and removal for Claude Code settings.json."""
from __future__ import annotations

import json
from pathlib import Path

AGENTLINT_HOOKS: dict = {
    "PreToolUse": [
        {
            "matcher": "Bash|Edit|Write",
            "hooks": [
                {
                    "type": "command",
                    "command": "agentlint check --event PreToolUse",
                    "timeout": 5,
                }
            ],
        }
    ],
    "PostToolUse": [
        {
            "matcher": "Edit|Write",
            "hooks": [
                {
                    "type": "command",
                    "command": "agentlint check --event PostToolUse",
                    "timeout": 10,
                }
            ],
        }
    ],
    "Stop": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "agentlint report",
                    "timeout": 30,
                }
            ],
        }
    ],
}


def settings_path(scope: str, project_dir: str | None = None) -> Path:
    """Return the path to the Claude Code settings file.

    scope="project" → <project_dir>/.claude/settings.json
    scope="user"    → ~/.claude/settings.json
    """
    if scope == "user":
        return Path.home() / ".claude" / "settings.json"
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ".claude" / "settings.json"


def read_settings(path: Path) -> dict:
    """Read and parse settings JSON. Returns {} if missing or invalid."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_settings(path: Path, data: dict) -> None:
    """Write settings JSON with indent=2. Creates parent dirs if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _is_agentlint_entry(entry: dict) -> bool:
    """Return True if a hook entry was installed by agentlint."""
    for hook in entry.get("hooks", []):
        if "agentlint" in hook.get("command", ""):
            return True
    return False


def merge_hooks(existing: dict) -> dict:
    """Merge agentlint hooks into existing settings (idempotent).

    - Removes any existing agentlint entries first (for clean updates)
    - Appends our entries from AGENTLINT_HOOKS
    - Preserves all non-agentlint entries
    """
    settings = dict(existing)
    hooks = dict(settings.get("hooks", {}))

    for event, our_entries in AGENTLINT_HOOKS.items():
        current = list(hooks.get(event, []))
        # Remove existing agentlint entries
        current = [e for e in current if not _is_agentlint_entry(e)]
        # Append ours
        current.extend(our_entries)
        hooks[event] = current

    settings["hooks"] = hooks
    return settings


def remove_hooks(existing: dict) -> dict:
    """Remove all agentlint hooks from settings.

    - Filters out agentlint entries, keeps everything else
    - Removes empty event keys and empty hooks dict
    """
    settings = dict(existing)
    hooks = dict(settings.get("hooks", {}))

    for event in list(hooks):
        filtered = [e for e in hooks[event] if not _is_agentlint_entry(e)]
        if filtered:
            hooks[event] = filtered
        else:
            del hooks[event]

    if hooks:
        settings["hooks"] = hooks
    else:
        settings.pop("hooks", None)

    return settings
