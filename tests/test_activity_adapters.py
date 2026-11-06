"""Host lifecycle contracts across every registered AgentLint adapter."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from agentlint.activity import observe, pending_context, snapshot
from agentlint.adapters import _ADAPTER_REGISTRY, get_adapter
from agentlint.models import AgentEvent


def payload(root, **changes):
    return {
        "session_id": "parent",
        "agent_id": "child",
        "tool_use_id": "call",
        "tool_name": "Bash",
        "tool_input": {"command": "printf confidential-value"},
        "cwd": str(root),
        **changes,
    }


@pytest.mark.parametrize("platform", sorted(_ADAPTER_REGISTRY))
def test_every_adapter_observes_normalized_host_events_without_approving(tmp_path, platform):
    adapter = get_adapter(platform)
    raw = payload(tmp_path)
    adapter.observe_activity(AgentEvent.PRE_TOOL_USE, raw, str(tmp_path))
    assert adapter.activity_status(str(tmp_path))["actions"][0]["state"] == "unknown"
    adapter.observe_activity(AgentEvent.PERMISSION_REQUEST, raw, str(tmp_path))
    waiting = adapter.activity_status(str(tmp_path), session_id="parent")
    assert waiting["actions"][0]["state"] == "awaiting_approval"
    text = pending_context(str(tmp_path), "parent", platform=platform)
    context = json.loads(
        adapter.formatter.add_activity_context(None, AgentEvent.SESSION_START, text)
    )
    assert "awaiting_approval" in json.dumps(context)
    assert context.get("permission") != "allow"
    assert context.get("decision") not in {"allow", "approve"}
    adapter.observe_activity(
        AgentEvent.POST_TOOL_FAILURE, {**raw, "error": "private-error"}, str(tmp_path)
    )
    assert adapter.activity_status(str(tmp_path))["actions"][0]["state"] == "tool_failed"
    assert "confidential-value" not in json.dumps(waiting)
    assert "private-error" not in json.dumps(adapter.activity_status(str(tmp_path)))


@pytest.mark.parametrize("platform", sorted(_ADAPTER_REGISTRY))
@pytest.mark.parametrize("state", ["running", "awaiting_approval", "unknown"])
def test_explicit_host_state_precedes_implicit_success(tmp_path, platform, state):
    adapter = get_adapter(platform)
    adapter.observe_activity(
        AgentEvent.POST_TOOL_USE, payload(tmp_path, tool_response={"status": state}), str(tmp_path)
    )
    assert adapter.activity_status(str(tmp_path))["actions"][0]["state"] == state


@pytest.mark.parametrize(
    "platform,kind", [("kimi", "permission_prompt"), ("gemini", "ToolPermission")]
)
def test_typed_notifications_report_wait_without_inventing_attribution(tmp_path, platform, kind):
    adapter = get_adapter(platform)
    adapter.observe_activity(
        "Notification",
        {
            "session_id": "parent",
            "cwd": str(tmp_path),
            "notification_type": kind,
            "message": "private-description",
        },
        str(tmp_path),
    )
    action = adapter.activity_status(str(tmp_path))["actions"][0]
    assert action["state"] == "awaiting_approval"
    assert action["agent_id"] is None
    assert action["action_fingerprint"] is None
    assert "private-description" not in json.dumps(action)


@pytest.mark.parametrize("platform", sorted(_ADAPTER_REGISTRY))
def test_idless_new_action_does_not_inherit_previous_terminal_state(tmp_path, platform):
    adapter = get_adapter(platform)
    raw = payload(tmp_path, tool_use_id=None, turn_id=None)
    adapter.observe_activity("PreToolUse", raw, str(tmp_path))
    adapter.observe_activity(
        "PermissionRequest", {**raw, "approval_owner": "previous-owner"}, str(tmp_path)
    )
    adapter.observe_activity(
        "PostToolUse", {**raw, "tool_response": {"exit_code": 0}}, str(tmp_path)
    )
    assert adapter.activity_status(str(tmp_path))["actions"][0]["state"] == "completed"
    adapter.observe_activity("PreToolUse", raw, str(tmp_path))
    action = adapter.activity_status(str(tmp_path))["actions"][0]
    assert action["state"] == "unknown"
    assert action["approval_owner"] is None and action["approval_observed"] is False


def test_grok_never_parses_free_text_notifications_as_approval(tmp_path):
    adapter = get_adapter("grok")
    adapter.observe_activity(
        "Notification", {"session_id": "parent", "message": "permission needed"}, str(tmp_path)
    )
    assert adapter.activity_status(str(tmp_path))["state"] == "unknown"


def test_cursor_normalizes_ids_and_uses_supported_context_channel(tmp_path):
    adapter = get_adapter("cursor")
    raw = payload(
        tmp_path,
        session_id=None,
        conversation_id="conversation",
        generation_id="generation",
        agent_id=None,
        subagent_id="child",
    )
    adapter.observe_activity("preToolUse", raw, str(tmp_path))
    adapter.observe_activity("postToolUseFailure", raw, str(tmp_path))
    action = adapter.activity_status(str(tmp_path), session_id="conversation")["actions"][0]
    assert action["state"] == "tool_failed"
    assert action["agent_id"] == "child"
    assert adapter.formatter.add_activity_context(None, AgentEvent.USER_PROMPT, "pending") is None
    assert json.loads(
        adapter.formatter.add_activity_context(None, AgentEvent.SESSION_START, "pending")
    )["additional_context"]


def test_kimi_tool_call_id_matches_tool_output_completion(tmp_path):
    adapter = get_adapter("kimi")
    raw = payload(tmp_path, tool_use_id=None, tool_call_id="kimi-call", tool_name="Shell")
    adapter.observe_activity("PreToolUse", raw, str(tmp_path))
    adapter.observe_activity("PostToolUse", {**raw, "tool_output": {"exit_code": 0}}, str(tmp_path))
    actions = adapter.activity_status(str(tmp_path))["actions"]
    assert len(actions) == 1 and actions[0]["state"] == "completed"


def test_grok_context_is_native_top_level_and_preserves_denial():
    formatter = get_adapter("grok").formatter
    result = json.loads(
        formatter.add_activity_context('{"decision":"deny"}', AgentEvent.POST_TOOL_USE, "pending")
    )
    assert result == {"decision": "deny", "additionalContext": "pending"}


def test_concurrent_child_hooks_preserve_all_pending_requests(tmp_path):
    def record(index):
        observe(
            payload(tmp_path, agent_id=f"child-{index}", tool_use_id=f"call-{index}"),
            event="PermissionRequest",
            project_dir=str(tmp_path),
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(record, range(24)))
    actions = snapshot(str(tmp_path))["actions"]
    assert len(actions) == 24
    assert all(item["state"] == "awaiting_approval" for item in actions)


@pytest.mark.parametrize("platform", sorted(_ADAPTER_REGISTRY))
def test_failure_event_precedes_contradictory_running_status(tmp_path, platform):
    adapter = get_adapter(platform)
    adapter.observe_activity(
        AgentEvent.POST_TOOL_FAILURE,
        payload(tmp_path, tool_response={"status": "running"}),
        str(tmp_path),
    )
    assert adapter.activity_status(str(tmp_path))["actions"][0]["state"] == "tool_failed"


def test_pending_evidence_outlives_bounded_terminal_history(tmp_path):
    observe(
        payload(tmp_path, tool_use_id="old-pending"),
        event="PermissionRequest",
        project_dir=str(tmp_path),
    )
    for index in range(1005):
        observe(
            payload(tmp_path, tool_use_id=f"finished-{index}", tool_response={"exit_code": 0}),
            event="PostToolUse",
            project_dir=str(tmp_path),
        )
    state = snapshot(str(tmp_path))
    assert state["truncated"] is True
    assert state["total"] == 1001
    assert state["actions"][0]["state"] == "awaiting_approval"


def test_corrupt_activity_storage_reports_unknown(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "activity.sqlite3").write_text("not a database")
    monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(cache))
    state = snapshot(str(tmp_path))
    assert state["state"] == "unknown" and state["error"]


def test_mcp_activity_reader_is_passive(tmp_path, monkeypatch):
    from agentlint.mcp_server import get_activity

    monkeypatch.setenv("AGENTLINT_PROJECT_DIR", str(tmp_path))
    assert json.loads(get_activity())["state"] == "unknown"
