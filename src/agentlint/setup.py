"""Hook installation and removal for Claude Code settings.json."""
from __future__ import annotations

import json
import shutil
import sys
import sysconfig
from pathlib import Path


def _resolve_command() -> str:
    """Resolve the absolute command to invoke agentlint.

    Probes multiple well-known locations in order:
    1. shutil.which() — PATH lookup
    2. ~/.local/bin/agentlint — pipx location
    3. ~/.local/share/uv/tools/agentlint/bin/agentlint — uv tool location
    4. sysconfig scripts dir — where pip puts console_scripts
       (covers Framework installs like /Library/Frameworks/Python.framework/)
    5. sys.executable -m agentlint — guaranteed to work with __main__.py
    """
    # 1. PATH lookup
    found = shutil.which("agentlint")
    if found:
        return found

    # 2. pipx location
    pipx = Path.home() / ".local" / "bin" / "agentlint"
    if pipx.is_file():
        return str(pipx)

    # 3. uv tool location
    uv_tool = Path.home() / ".local" / "share" / "uv" / "tools" / "agentlint" / "bin" / "agentlint"
    if uv_tool.is_file():
        return str(uv_tool)

    # 4. sysconfig scripts dir (where pip installs console_scripts)
    scripts_dir = sysconfig.get_path("scripts")
    if scripts_dir:
        scripts_bin = Path(scripts_dir) / "agentlint"
        if scripts_bin.is_file():
            return str(scripts_bin)

    # 5. python -m fallback (works with __main__.py)
    return f"{sys.executable} -m agentlint"


def build_hooks(cmd: str) -> dict:
    """Build the agentlint hooks dict with the given command."""
    return {
        "PreToolUse": [
            {
                "matcher": "Bash|Edit|Write",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{cmd} check --event PreToolUse",
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
                        "command": f"{cmd} check --event PostToolUse",
                        "timeout": 10,
                    }
                ],
            }
        ],
        "UserPromptSubmit": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{cmd} check --event UserPromptSubmit",
                        "timeout": 5,
                    }
                ],
            }
        ],
        "SubagentStop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{cmd} check --event SubagentStop",
                        "timeout": 10,
                    }
                ],
            }
        ],
        "Notification": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{cmd} check --event Notification",
                        "timeout": 5,
                    }
                ],
            }
        ],
        "Stop": [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{cmd} report",
                        "timeout": 30,
                    }
                ],
            }
        ],
    }


# Backward-compatible alias for external consumers
AGENTLINT_HOOKS: dict = build_hooks("agentlint")


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


def merge_hooks(existing: dict, agentlint_cmd: str | None = None) -> dict:
    """Merge agentlint hooks into existing settings (idempotent).

    - Removes any existing agentlint entries first (for clean updates)
    - Builds hook entries using the resolved agentlint command
    - Preserves all non-agentlint entries
    """
    cmd = agentlint_cmd or _resolve_command()
    hooks_template = build_hooks(cmd)

    settings = dict(existing)
    hooks = dict(settings.get("hooks", {}))

    for event, our_entries in hooks_template.items():
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
