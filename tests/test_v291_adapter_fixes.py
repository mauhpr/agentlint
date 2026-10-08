"""Regression tests for adapter setup output, Gemini event names and safe installs."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from agentlint.adapters import get_adapter
from agentlint.adapters.mcp import _mcp_command
from agentlint.cli import main
from agentlint.formats.gemini_hooks import GeminiHookFormatter
from agentlint.models import AgentEvent, Severity, Violation


def _echoed(fn):
    with patch("click.echo") as echo:
        fn()
    return "\n".join(str(c.args[0]) for c in echo.call_args_list if c.args)


def test_setup_mcp_prints_mcp_server_and_absolute_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    text = _echoed(lambda: get_adapter("mcp").install_hooks(".", cmd="/opt/venv/bin/agentlint"))
    config = json.loads(text[text.index("{") :])["mcpServers"]["agentlint"]
    assert config["command"] == "agentlint-mcp"
    assert config["env"]["AGENTLINT_PROJECT_DIR"] == str(tmp_path)


def test_mcp_command_prefers_sibling_binary(tmp_path):
    (tmp_path / "agentlint").write_text("")
    (tmp_path / "agentlint-mcp").write_text("")
    assert _mcp_command(str(tmp_path / "agentlint")) == str(tmp_path / "agentlint-mcp")
    assert _mcp_command("/x/agentlint-mcp") == "/x/agentlint-mcp"
    assert _mcp_command(None) == "agentlint-mcp"


@pytest.mark.parametrize("platform", ["mcp", "generic", "openai"])
def test_setup_does_not_claim_hooks_for_snippet_adapters(tmp_path, platform):
    result = CliRunner().invoke(main, ["setup", platform, "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Installed AgentLint hooks" not in result.output
    assert "No files were changed" in result.output


@pytest.mark.parametrize(
    ("event", "native"),
    [
        (AgentEvent.POST_TOOL_USE, "AfterTool"),
        (AgentEvent.USER_PROMPT, "BeforeAgent"),
        ("AfterTool", "AfterTool"),
        (AgentEvent.NOTIFICATION, "Notification"),
    ],
)
def test_gemini_output_uses_native_event_names(event, native):
    warning = Violation(rule_id="r", message="m", severity=Severity.WARNING)
    out = json.loads(GeminiHookFormatter().format([warning], event))
    assert out["hookSpecificOutput"]["hookEventName"] == native


def test_gemini_pre_tool_error_still_denies():
    error = Violation(rule_id="r", message="m", severity=Severity.ERROR)
    out = json.loads(GeminiHookFormatter().format([error], AgentEvent.PRE_TOOL_USE))
    assert out["decision"] == "deny"


@pytest.mark.parametrize(
    ("platform", "path", "content"),
    [
        ("claude", ".claude/settings.json", "{ not json"),
        ("codex", ".codex/hooks.json", "[1, 2]"),
        ("cursor", ".cursor/hooks.json", "{oops"),
        ("gemini", ".gemini/settings.json", "{oops"),
        ("continue", ".continue/settings.json", "{oops"),
        ("grok", ".grok/settings.json", "{oops"),
        ("kimi", ".kimi/config.toml", "this = = not toml"),
    ],
)
def test_setup_refuses_to_overwrite_unreadable_settings(tmp_path, platform, path, content):
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text(content)
    result = CliRunner().invoke(main, ["setup", platform, "--project-dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "will not overwrite" in result.output
    assert target.read_text() == content
