"""Failure paths must preserve policy decisions and passive native approval behavior."""

from __future__ import annotations

import json
import sqlite3

import pytest
from click.testing import CliRunner

from agentlint.activity import observe, pending_context, snapshot
from agentlint.adapters import get_adapter
from agentlint.adapters.codex import CodexAdapter
from agentlint.cli import main


def payload(root, **changes):
    return {
        "session_id": "parent",
        "agent_id": "child",
        "tool_use_id": "call",
        "tool_name": "Bash",
        "tool_input": {"command": "printf private-value"},
        "cwd": str(root),
        **changes,
    }


def invoke_observer(root, event="PermissionRequest", data=None, adapter="codex"):
    return CliRunner().invoke(
        main,
        ["observe", "--event", event, "--adapter", adapter, "--project-dir", str(root)],
        input=data if isinstance(data, str) else json.dumps(data or payload(root)),
    )


@pytest.mark.parametrize("data", ["[]", "null", "{invalid"])
def test_malformed_observation_abstains_from_native_permission_decision(tmp_path, data):
    result = invoke_observer(tmp_path, data=data)
    assert result.exit_code == 0
    assert not result.stdout
    assert "unknown" in result.stderr


def test_observer_accepts_normalized_event_names_without_an_approval(tmp_path):
    result = invoke_observer(
        tmp_path, "post_tool_use", payload(tmp_path, tool_response={"exit_code": 0})
    )
    assert result.exit_code == 0 and not result.stdout
    assert snapshot(str(tmp_path))["actions"][0]["state"] == "completed"


def test_passive_tool_result_surfaces_other_pending_child_without_resubmission(tmp_path):
    assert not invoke_observer(tmp_path).stdout
    result = invoke_observer(
        tmp_path,
        "PostToolUse",
        payload(tmp_path, tool_use_id="parent-call", agent_id=None, tool_response={"exit_code": 0}),
    )
    output = json.loads(result.stdout)
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "PostToolUse"
    assert "do not interrupt or resubmit" in specific["additionalContext"]
    assert "decision" not in output and "permissionDecision" not in specific
    assert len(snapshot(str(tmp_path))["actions"]) == 2


def test_passive_subagent_stop_returns_only_native_empty_json(tmp_path):
    result = invoke_observer(tmp_path, "SubagentStop")
    assert result.exit_code == 0 and json.loads(result.stdout) == {}
    assert snapshot(str(tmp_path))["agents"][0]["state"] == "completed"


def test_activity_storage_failure_cannot_hide_actual_rule_denial(tmp_path, monkeypatch, caplog):
    (tmp_path / "agentlint.yml").write_text("packs: [security]\n")

    def unavailable(*args, **kwargs):
        raise sqlite3.OperationalError("private-storage-detail")

    monkeypatch.setattr(CodexAdapter, "observe_activity", unavailable)
    raw = payload(tmp_path, tool_input={"command": "cp source maintained.py"})
    result = CliRunner().invoke(
        main,
        ["check", "--event", "PreToolUse", "--adapter", "codex", "--project-dir", str(tmp_path)],
        input=json.dumps(raw),
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "unknown" in caplog.text
    assert "private-storage-detail" not in result.output + caplog.text


def test_corrupt_activity_is_unknown_in_parent_context_and_human_status(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "activity.sqlite3").write_text("corrupt-data")
    monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(cache))
    assert "unknown" in pending_context(str(tmp_path), "parent")
    result = CliRunner().invoke(main, ["status", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0 and "Activity observations unavailable" in result.output


def test_human_status_shows_known_subagent_lifecycle(tmp_path):
    observe(payload(tmp_path), event="SubagentStart", project_dir=str(tmp_path))
    result = CliRunner().invoke(main, ["status", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "agent=child: unknown (last lifecycle event)" in result.stdout


@pytest.mark.parametrize(
    "metadata,state",
    [
        ({"failure_type": "permission_denied"}, "host_denied"),
        ({"tool_response": {"status": "declined"}}, "host_denied"),
        ({"is_interrupt": True}, "cancelled"),
        ({"tool_response": {"status": "cancelled"}}, "cancelled"),
    ],
)
def test_native_denial_and_interrupt_clear_pending_observation(tmp_path, metadata, state):
    observe(payload(tmp_path), event="PermissionRequest", project_dir=str(tmp_path))
    observe(payload(tmp_path, **metadata), event="PostToolUseFailure", project_dir=str(tmp_path))
    item = snapshot(str(tmp_path))["actions"][0]
    assert item["state"] == state and item["approval_observed"] is False
    assert pending_context(str(tmp_path), "parent") is None
    observe(payload(tmp_path), event="PermissionRequest", project_dir=str(tmp_path))
    assert snapshot(str(tmp_path))["actions"][0]["state"] == state


def test_exact_call_id_preserves_known_owner_and_actor_when_result_omits_them(tmp_path):
    observe(
        payload(tmp_path, approval_owner="human"),
        event="PermissionRequest",
        project_dir=str(tmp_path),
    )
    observe(
        payload(tmp_path, agent_id=None, tool_response={"status": "unknown"}),
        event="PostToolUse",
        project_dir=str(tmp_path),
    )
    item = snapshot(str(tmp_path))["actions"][0]
    assert item["agent_id"] == "child" and item["approval_owner"] == "human"
    assert item["approval_observed"] is True


def test_unsafe_identity_labels_are_fingerprinted_not_echoed(tmp_path):
    observe(
        payload(tmp_path, agent_id="private / identity", approval_owner="private owner value"),
        event="PermissionRequest",
        project_dir=str(tmp_path),
    )
    state = snapshot(str(tmp_path))
    assert state["actions"][0]["agent_id"].startswith("id-")
    assert "private / identity" not in json.dumps(state)
    assert "private owner value" not in json.dumps(state)


def test_parent_reminder_reports_truncated_observations(tmp_path):
    for index in range(101):
        observe(
            payload(tmp_path, tool_use_id=f"call-{index}"),
            event="PermissionRequest",
            project_dir=str(tmp_path),
        )
    context = pending_context(str(tmp_path), "parent")
    assert "100 of 101 observations" in context
    assert "do not interrupt or resubmit" in context


@pytest.mark.parametrize(
    "output,expected", [('{"exit_code":0}', "completed"), ("not JSON output", "unknown")]
)
def test_cursor_serialized_output_is_decoded_or_safely_unknown(tmp_path, output, expected):
    adapter = get_adapter("cursor")
    adapter.observe_activity("postToolUse", payload(tmp_path, tool_output=output), str(tmp_path))
    item = adapter.activity_status(str(tmp_path))["actions"][0]
    assert item["state"] == expected
