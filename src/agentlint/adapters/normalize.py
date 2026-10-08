"""Translate native tool calls into the canonical names built-in rules check.

Built-in rules are written against the canonical tool names `Bash`, `Write` and
`Edit` and their input keys (`command`, `file_path`, `content`, `old_string`,
`new_string`). Agents such as Gemini, Kimi, Grok and Cursor use their own names
(`run_shell_command`, `Shell`, `WriteFile`, ...). Without this translation those
calls matched no built-in rule at all.
"""

from __future__ import annotations

from agentlint.core.models import NormalizedTool

_CANONICAL = {
    NormalizedTool.SHELL.value: "Bash",
    NormalizedTool.FILE_WRITE.value: "Write",
    NormalizedTool.FILE_EDIT.value: "Edit",
}

# Canonical input key -> native aliases, tried in order. Only filled in when the
# canonical key is missing; the native keys are kept.
_INPUT_ALIASES = {
    "command": ("cmd", "script", "commandLine", "command_line"),
    "file_path": ("path", "filePath", "absolute_path", "file", "filename", "target_file"),
    "content": ("contents", "text", "file_text", "new_content"),
    "old_string": ("old_str", "oldText", "old_text", "search"),
    "new_string": ("new_str", "newText", "new_text", "replace", "replacement"),
}


def canonical_tool_call(adapter, tool_name: str, tool_input: dict) -> tuple[str, dict]:
    """Return (canonical tool name, tool input with canonical keys added)."""
    if not isinstance(tool_name, str) or tool_name in {"Bash", "Write", "Edit"}:
        return tool_name, tool_input
    try:
        normalized = adapter.normalize_tool_name(tool_name)
    except Exception:  # noqa: BLE001 - unknown tools keep their native name
        return tool_name, tool_input
    canonical = _CANONICAL.get(normalized)
    if canonical is None or not isinstance(tool_input, dict):
        return tool_name, tool_input
    if tool_name == "apply_patch":
        return tool_name, tool_input  # Codex patches are expanded separately
    translated = dict(tool_input)
    for key, aliases in _INPUT_ALIASES.items():
        if key in translated:
            continue
        for alias in aliases:
            value = translated.get(alias)
            if isinstance(value, str):
                translated[key] = value
                break
    return canonical, translated
