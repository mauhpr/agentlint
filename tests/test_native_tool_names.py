"""Built-in rules must fire for every agent's native tool names."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from agentlint.adapters import get_adapter
from agentlint.adapters.normalize import canonical_tool_call
from agentlint.cli import main

SECRET = 'API_KEY = "sk_live_abc123def456ghi789"\n'

SHELL_TOOLS = [
    ("claude", "Bash"),
    ("codex", "Bash"),
    ("continue", "Bash"),
    ("gemini", "run_shell_command"),
    ("gemini", "bash"),
    ("kimi", "Shell"),
    ("grok", "bash"),
    ("cursor", "Shell"),
]
WRITE_TOOLS = [
    ("claude", "Write", {}),
    ("gemini", "write_file", {}),
    ("kimi", "WriteFile", {}),
    ("grok", "write", {}),
    ("cursor", "Write", {}),
    ("gemini", "write_file", {"use_path_alias": True}),
]


def _check(tmp_path, adapter, payload, event="PreToolUse"):
    result = CliRunner().invoke(
        main,
        ["check", "--adapter", adapter, "--event", event, "--project-dir", str(tmp_path)],
        input=json.dumps({**payload, "cwd": str(tmp_path)}),
    )
    return result.output


def _event(adapter):
    return {"gemini": "BeforeTool", "cursor": "preToolUse"}.get(adapter, "PreToolUse")


@pytest.mark.parametrize(("adapter", "tool"), SHELL_TOOLS)
def test_force_push_is_blocked_for_native_shell_tools(tmp_path, adapter, tool):
    payload = {"tool_name": tool, "tool_input": {"command": "git push --force origin main"}}
    assert "no-force-push" in _check(tmp_path, adapter, payload, _event(adapter))


@pytest.mark.parametrize(("adapter", "tool", "opts"), WRITE_TOOLS)
def test_secret_write_is_blocked_for_native_write_tools(tmp_path, adapter, tool, opts):
    path_key = "path" if opts.get("use_path_alias") else "file_path"
    payload = {
        "tool_name": tool,
        "tool_input": {path_key: str(tmp_path / "c.py"), "content": SECRET},
    }
    assert "no-secrets" in _check(tmp_path, adapter, payload, _event(adapter))


def test_canonicalization_keeps_native_keys_and_unknown_tools():
    gemini = get_adapter("gemini")
    name, data = canonical_tool_call(
        gemini, "replace", {"path": "a.py", "old_str": "x", "new_str": "y"}
    )
    assert name == "Edit"
    assert data == {
        "path": "a.py",
        "old_str": "x",
        "new_str": "y",
        "file_path": "a.py",
        "old_string": "x",
        "new_string": "y",
    }
    assert canonical_tool_call(gemini, "read_file", {"path": "a"}) == ("read_file", {"path": "a"})
    assert canonical_tool_call(gemini, "mystery", {}) == ("mystery", {})
    assert canonical_tool_call(get_adapter("codex"), "apply_patch", {"command": "x"}) == (
        "apply_patch",
        {"command": "x"},
    )
    assert canonical_tool_call(gemini, "Bash", {"command": "ls"}) == ("Bash", {"command": "ls"})
