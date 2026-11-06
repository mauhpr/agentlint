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


def activity_payload(adapter, raw: dict) -> dict:
    """Normalize documented host lifecycle fields without reading transcripts or messages."""
    import json

    payload = dict(raw)
    platform = adapter.platform_name
    if platform == "cursor":
        payload["session_id"] = raw.get("conversation_id") or raw.get("session_id")
        payload["turn_id"] = raw.get("generation_id")
        payload["agent_id"] = raw.get("subagent_id") or raw.get("agent_id")
    if platform == "kimi":
        payload["tool_use_id"] = raw.get("tool_call_id") or raw.get("tool_use_id")
    if platform in {"cursor", "kimi", "grok"} and "tool_response" not in payload:
        response = raw.get("tool_output")
        if isinstance(response, str):
            try:
                response = json.loads(response)
            except ValueError:
                response = None
        payload["tool_response"] = response if isinstance(response, dict) else None
    tool = raw.get("tool_name") or raw.get("function_name") or raw.get("name") or ""
    inputs = raw.get("tool_input") or raw.get("arguments") or {}
    payload["tool_name"], payload["tool_input"] = canonical_tool_call(adapter, tool, inputs)
    return payload
