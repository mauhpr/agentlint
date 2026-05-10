"""Privacy contract tests for agentlint.agentchute.

These tests verify by inspection of the actual HTTP request body that
the AgentChute sync layer NEVER transmits:

  - Raw file content (Write/Edit ``content`` field)
  - Raw old_string/new_string (Edit/MultiEdit fields)
  - Raw prompts (UserPromptSubmit ``prompt`` field beyond a 100-char preview)
  - Bash commands beyond 200 chars

The tests work by monkey-patching ``requests.post`` so we capture the
JSON body that *would* have been sent without making real network calls.

If you change the privacy posture (new event field, longer truncation,
etc.), update both ``recorder.summarize_tool_input`` AND these tests.
The tests are intentionally strict — failing them is a security incident.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ---------- helpers ----------


SECRET_FILE_CONTENT = (
    "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"
    "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY\n"
    "DATABASE_URL=postgres://user:hunter2@db.example.com/prod\n"
)
LONG_BASH_COMMAND = "rm -rf " + ("/very/long/path/" * 100) + " --dangerous-flag"
LONG_PROMPT = (
    "Please refactor the entire codebase to use the new pattern. "
    "Here is the full diff that needs to be applied: "
) + ("DIFFLINE\n" * 200)


@pytest.fixture
def agentchute_env(monkeypatch):
    """Activate AgentChute sync with a fake license key + URL."""
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
    monkeypatch.setenv("AGENTCHUTE_API_URL", "https://api.example.test/v1")
    monkeypatch.setenv("AGENTCHUTE_ENABLED", "true")
    yield


@pytest.fixture
def captured_post():
    """Patch requests.post and capture the JSON body of every call.

    Yields a list to which each captured body dict is appended.
    """
    captured: list[dict] = []

    def _capture(*args, **kwargs):
        body = kwargs.get("json")
        if body is not None:
            captured.append(body)
        # Return a fake successful response.
        response = MagicMock()
        response.status_code = 200
        return response

    with patch("requests.post", side_effect=_capture):
        yield captured


# ---------- summarize_tool_input — the privacy chokepoint ----------


def test_summarize_strips_write_content():
    """Write events must not transmit the file content. Only path + length."""
    from agentlint.recorder import summarize_tool_input

    summary = summarize_tool_input(
        "Write",
        {"file_path": "/etc/secrets.env", "content": SECRET_FILE_CONTENT},
    )
    serialized = json.dumps(summary)
    assert "AKIAIOSFODNN" not in serialized
    assert "hunter2" not in serialized
    assert "DATABASE_URL" not in serialized
    assert summary["content_length"] == len(SECRET_FILE_CONTENT)


def test_summarize_strips_edit_old_and_new_strings():
    """Edit events must transmit lengths only, not raw old/new strings."""
    from agentlint.recorder import summarize_tool_input

    summary = summarize_tool_input(
        "Edit",
        {
            "file_path": "/etc/secrets.env",
            "old_string": SECRET_FILE_CONTENT,
            "new_string": SECRET_FILE_CONTENT + "EXTRA_SECRET=topsecret",
        },
    )
    serialized = json.dumps(summary)
    assert "AKIAIOSFODNN" not in serialized
    assert "hunter2" not in serialized
    assert "EXTRA_SECRET" not in serialized
    assert "topsecret" not in serialized
    # Lengths are present and accurate.
    assert summary["content_length"] == len(SECRET_FILE_CONTENT) + len(
        "EXTRA_SECRET=topsecret"
    )
    assert summary["old_content_length"] == len(SECRET_FILE_CONTENT)


def test_summarize_truncates_long_bash_commands():
    """Bash commands must be capped at 200 chars even if the input is huge."""
    from agentlint.recorder import summarize_tool_input

    summary = summarize_tool_input("Bash", {"command": LONG_BASH_COMMAND})
    assert summary["command"] is not None
    assert len(summary["command"]) <= 200


def test_summarize_truncates_user_prompt_preview():
    """User prompts are previewed at 100 chars, never transmitted in full."""
    from agentlint.recorder import summarize_tool_input

    summary = summarize_tool_input(
        "UserPromptSubmit",
        {},
        prompt=LONG_PROMPT,
    )
    preview = summary.get("prompt_preview")
    assert preview is not None
    assert len(preview) <= 100
    assert "DIFFLINE" not in preview or preview.count("DIFFLINE") < 13  # tight bound


# ---------- end-to-end: data sent through AgentChuteClient.post_event ----------


def test_post_event_does_not_leak_file_content(agentchute_env, captured_post):
    """Integration check: the captured HTTP body for a Write event
    contains no file content."""
    from agentlint.agentchute import post_event_async
    import threading

    # Build the same shape cli.py builds when agentchute_needed is true.
    from agentlint.recorder import summarize_tool_input

    event = {
        "session_key": "test-session",
        "event": {
            "v": 1,
            "ts": 1700000000.0,
            "event": "PreToolUse",
            "tool_name": "Write",
            "tool_summary": summarize_tool_input(
                "Write",
                {"file_path": "/etc/secrets.env", "content": SECRET_FILE_CONTENT},
            ),
            "violations": [],
            "rules_evaluated": ["no-secrets"],
            "is_blocking": False,
            "project_dir": "/repo",
        },
    }
    post_event_async(event)
    # post_event_async fires a daemon thread; wait briefly for it to flush.
    for t in threading.enumerate():
        if t.name == "agentlint-agentchute-post":
            t.join(timeout=2.0)

    assert len(captured_post) == 1, "expected exactly one POST to be captured"
    body_str = json.dumps(captured_post[0])
    assert "AKIAIOSFODNN" not in body_str
    assert "hunter2" not in body_str
    assert "DATABASE_URL" not in body_str
    assert SECRET_FILE_CONTENT not in body_str


def test_post_event_does_not_leak_long_bash(agentchute_env, captured_post):
    """Bash commands above 200 chars must be truncated before POST."""
    from agentlint.agentchute import post_event_async
    from agentlint.recorder import summarize_tool_input
    import threading

    event = {
        "session_key": "test-session",
        "event": {
            "v": 1,
            "tool_name": "Bash",
            "tool_summary": summarize_tool_input(
                "Bash",
                {"command": LONG_BASH_COMMAND},
            ),
        },
    }
    post_event_async(event)
    for t in threading.enumerate():
        if t.name == "agentlint-agentchute-post":
            t.join(timeout=2.0)

    assert len(captured_post) == 1
    body = captured_post[0]
    cmd_in_body = body["event"]["tool_summary"]["command"]
    assert cmd_in_body is not None
    assert len(cmd_in_body) <= 200
    # The dangerous-flag tail of the original command must NOT appear:
    # if it did, it'd mean we sent the full untruncated command.
    assert "--dangerous-flag" not in cmd_in_body


def test_post_event_does_not_leak_full_prompt(agentchute_env, captured_post):
    """UserPromptSubmit prompts must never transmit beyond the 100-char preview."""
    from agentlint.agentchute import post_event_async
    from agentlint.recorder import summarize_tool_input
    import threading

    event = {
        "session_key": "test-session",
        "event": {
            "v": 1,
            "tool_name": "UserPromptSubmit",
            "tool_summary": summarize_tool_input(
                "UserPromptSubmit",
                {},
                prompt=LONG_PROMPT,
            ),
        },
    }
    post_event_async(event)
    for t in threading.enumerate():
        if t.name == "agentlint-agentchute-post":
            t.join(timeout=2.0)

    assert len(captured_post) == 1
    body_str = json.dumps(captured_post[0])
    # The prompt has 200+ DIFFLINE markers; the preview can hold ~12 at most.
    # If the full prompt leaked, we'd see far more.
    assert body_str.count("DIFFLINE") < 13


# ---------- opt-in gate: no traffic when feature is off ----------


def test_no_post_when_license_key_missing(captured_post, monkeypatch):
    """If the user has no license key, post_event_async must be a no-op
    even if AGENTCHUTE_ENABLED=true is set."""
    from agentlint.agentchute import post_event_async

    monkeypatch.setenv("AGENTCHUTE_ENABLED", "true")
    monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)

    post_event_async({"session_key": "should-not-fire", "event": {}})
    # Wait briefly to be sure no thread fires.
    import time

    time.sleep(0.1)
    assert captured_post == []


def test_no_post_when_explicitly_disabled(captured_post, monkeypatch):
    """AGENTCHUTE_ENABLED=false must override config defaults."""
    from agentlint.agentchute import post_event_async

    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
    monkeypatch.setenv("AGENTCHUTE_ENABLED", "false")

    post_event_async({"session_key": "should-not-fire", "event": {}})
    import time

    time.sleep(0.1)
    is_enabled = _check_is_agentchute_enabled_with_envs()
    assert is_enabled is False
    assert captured_post == []


def test_agentchute_env_enables_post(captured_post, monkeypatch):
    """AgentChute-named env vars are the public paid-product interface."""
    from agentlint.agentchute import post_event_async
    import threading

    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
    monkeypatch.setenv("AGENTCHUTE_API_URL", "https://api.example.test/v1")
    monkeypatch.setenv("AGENTCHUTE_ENABLED", "true")

    post_event_async({"session_key": "test-session", "event": {"v": 1}})
    for t in threading.enumerate():
        if t.name == "agentlint-agentchute-post":
            t.join(timeout=2.0)

    assert len(captured_post) == 1


def test_agentchute_config_enables_post(captured_post, monkeypatch):
    """agentchute.enabled in config enables posting when a license exists."""
    from agentlint.config import AgentLintConfig
    from agentlint.agentchute import post_event_async
    import threading

    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
    monkeypatch.setenv("AGENTCHUTE_API_URL", "https://api.example.test/v1")
    monkeypatch.delenv("AGENTCHUTE_ENABLED", raising=False)

    post_event_async(
        {"session_key": "test-session", "event": {"v": 1}},
        config=AgentLintConfig(agentchute={"enabled": True}),
    )
    for t in threading.enumerate():
        if t.name == "agentlint-agentchute-post":
            t.join(timeout=2.0)

    assert len(captured_post) == 1


def _check_is_agentchute_enabled_with_envs():
    from agentlint.agentchute import is_agentchute_enabled

    return is_agentchute_enabled(config=None)


# ---------- failure modes: API errors don't propagate ----------


def test_post_swallows_network_errors(monkeypatch):
    """If the API is unreachable, post_event_async must return immediately
    and never raise. The lint hot path depends on this."""
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
    monkeypatch.setenv("AGENTCHUTE_API_URL", "https://api.example.test/v1")
    monkeypatch.setenv("AGENTCHUTE_ENABLED", "true")

    import requests

    def _raise(*a, **k):
        raise requests.exceptions.ConnectionError("simulated DNS failure")

    with patch("requests.post", side_effect=_raise):
        from agentlint.agentchute import post_event_async

        # Should NOT raise; should NOT block.
        post_event_async({"session_key": "test", "event": {"foo": "bar"}})
        import time

        time.sleep(0.1)  # let the daemon thread complete
    # If we got here without a propagated exception, the test passes.
