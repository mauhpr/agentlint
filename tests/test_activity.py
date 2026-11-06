"""Observe native approval waits without becoming an approval controller."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from agentlint.cli import main


def _hook(root, event, *, adapter, **changes):
    payload = {
        "session_id": "parent-session",
        "agent_id": "child-agent",
        "turn_id": "turn-1",
        "tool_use_id": "call-1",
        "tool_name": "Bash",
        "tool_input": {"command": "printf private-command-value"},
        "cwd": str(root),
        **changes,
    }
    command = (
        "observe" if event in {"PermissionRequest", "SubagentStart", "SubagentStop"} else "check"
    )
    result = CliRunner().invoke(
        main,
        [command, "--event", event, "--adapter", adapter, "--project-dir", str(root)],
        input=json.dumps(payload),
    )
    assert result.exit_code == 0, result.output
    return result


@pytest.fixture(params=["codex", "claude"])
def hook(request):
    from functools import partial

    return partial(_hook, adapter=request.param)


def status(root):
    result = CliRunner().invoke(main, ["status", "--json", "--project-dir", str(root)])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)["activity"]


def test_parent_sees_pending_child_and_resume_preserves_one_request(tmp_path, hook):
    hook(tmp_path, "PreToolUse")
    pending = hook(tmp_path, "PermissionRequest", approval_owner="human")
    assert not pending.output
    hook(tmp_path, "PermissionRequest", approval_owner="human")
    before = status(tmp_path)
    assert len(before["actions"]) == 1
    action = before["actions"][0]
    assert action["state"] == "awaiting_approval"
    assert action["agent_id"] == "child-agent"
    assert action["approval_owner"] == "human"
    assert action["action_fingerprint"]
    resume = hook(tmp_path, "SessionStart", source="resume", tool_input={})
    assert "awaiting_approval" in resume.output
    assert "do not interrupt or resubmit" in resume.output
    assert status(tmp_path)["actions"] == before["actions"]
    assert "private-command-value" not in json.dumps(before)


def test_completion_and_duplicate_notifications_do_not_reopen_approval(tmp_path, hook):
    hook(tmp_path, "PermissionRequest")
    hook(tmp_path, "PostToolUse", tool_response={"exit_code": 0})
    hook(tmp_path, "PostToolUse", tool_response={"exit_code": 0})
    hook(tmp_path, "PermissionRequest")
    actions = status(tmp_path)["actions"]
    assert len(actions) == 1
    assert actions[0]["state"] == "completed"


def test_block_failure_and_unknown_are_distinct(tmp_path, hook):
    (tmp_path / "agentlint.yml").write_text("packs: [security]\n")
    hook(tmp_path, "PreToolUse", tool_input={"command": "cp src maintained.py"})
    assert status(tmp_path)["actions"][0]["state"] == "agentlint_blocked"
    hook(tmp_path, "PostToolUse", tool_use_id="call-2", tool_response={"exit_code": 1})
    hook(tmp_path, "PreToolUse", tool_use_id="call-3")
    states = {a["state"] for a in status(tmp_path)["actions"]}
    assert states == {"agentlint_blocked", "tool_failed", "unknown"}


def test_missing_attribution_is_unknown_and_projects_are_isolated(tmp_path, hook):
    hook(tmp_path, "PermissionRequest", agent_id=None)
    action = status(tmp_path)["actions"][0]
    assert action["agent_id"] is None
    assert action["approval_owner"] is None
    other = tmp_path / "other"
    other.mkdir()
    assert status(other)["actions"] == []


def test_subagent_without_tool_state_is_unknown(tmp_path, hook):
    hook(tmp_path, "SubagentStart", tool_input={})
    assert status(tmp_path)["agents"][0]["state"] == "unknown"


def test_idless_late_notification_does_not_resurrect_completed_request(tmp_path, hook):
    hook(tmp_path, "PreToolUse")
    hook(tmp_path, "PermissionRequest", tool_use_id=None)
    hook(tmp_path, "PostToolUse", tool_response={"exit_code": 0})
    hook(tmp_path, "PermissionRequest", tool_use_id=None)
    actions = status(tmp_path)["actions"]
    assert "awaiting_approval" not in {item["state"] for item in actions}
    assert {item["state"] for item in actions} == {"completed", "unknown"}


def test_missing_permission_metadata_does_not_leave_an_attributed_wait(tmp_path, hook):
    hook(tmp_path, "PreToolUse")
    hook(tmp_path, "PermissionRequest", tool_use_id=None, turn_id=None, agent_id=None)
    assert status(tmp_path)["actions"][0]["agent_id"] is None
    hook(tmp_path, "PostToolUse", tool_response={"exit_code": 0})
    actions = status(tmp_path)["actions"]
    assert len(actions) == 1
    assert actions[0]["state"] == "completed"


def test_orphan_approval_with_missing_metadata_binds_to_known_completion(tmp_path, hook):
    hook(tmp_path, "PermissionRequest", tool_use_id=None, turn_id=None, agent_id=None)
    hook(tmp_path, "PostToolUse", tool_response={"exit_code": 0})
    actions = status(tmp_path)["actions"]
    assert len(actions) == 1 and actions[0]["state"] == "completed"


def test_unknown_tool_response_preserves_pending_evidence_on_resume(tmp_path, hook):
    hook(tmp_path, "PermissionRequest")
    hook(tmp_path, "PostToolUse", tool_response={"status": "unknown"})
    item = status(tmp_path)["actions"][0]
    assert item["state"] == "unknown"
    assert item["approval_observed"] is True
    resume = hook(tmp_path, "SessionStart", source="resume", tool_input={})
    assert "do not interrupt or resubmit" in resume.output


def test_status_is_readonly_without_observations(tmp_path, monkeypatch):
    cache = tmp_path / "absent-cache"
    monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(cache))
    assert status(tmp_path)["state"] == "unknown"
    assert not cache.exists()


def test_real_permission_payload_without_invocation_id_correlates_to_completion(tmp_path, hook):
    hook(tmp_path, "PreToolUse")
    hook(tmp_path, "PermissionRequest", tool_use_id=None)
    actions = status(tmp_path)["actions"]
    assert len(actions) == 1
    assert actions[0]["state"] == "awaiting_approval"
    assert actions[0]["correlation"] == "unique_action_match"
    hook(tmp_path, "PostToolUse", tool_response={"exit_code": 0})
    assert len(status(tmp_path)["actions"]) == 1
    assert status(tmp_path)["actions"][0]["state"] == "completed"


def test_approval_without_pre_hook_binds_to_later_exact_completion(tmp_path, hook):
    hook(tmp_path, "PermissionRequest", tool_use_id=None)
    hook(tmp_path, "PostToolUse", tool_response={"exit_code": 0})
    hook(tmp_path, "PostToolUse", tool_response={"exit_code": 0})
    assert len(status(tmp_path)["actions"]) == 1
    assert status(tmp_path)["actions"][0]["state"] == "completed"


def test_ambiguous_parallel_actions_do_not_guess_which_child_is_waiting(tmp_path, hook):
    hook(tmp_path, "PreToolUse", tool_use_id="call-a")
    hook(tmp_path, "PreToolUse", tool_use_id="call-b")
    hook(tmp_path, "PermissionRequest", tool_use_id=None)
    uncertain = [a for a in status(tmp_path)["actions"] if a["correlation"] == "ambiguous"]
    assert len(uncertain) == 1
    assert uncertain[0]["state"] == "unknown"


def test_platforms_do_not_share_pending_requests(tmp_path):
    _hook(tmp_path, "PermissionRequest", adapter="claude")
    resume = _hook(tmp_path, "SessionStart", adapter="codex", source="resume", tool_input={})
    assert "awaiting_approval" not in resume.output


def test_claude_installs_passive_approval_and_failure_hooks():
    from agentlint.adapters.claude import _build_hooks

    hooks = _build_hooks("agentlint")
    assert (
        "observe --event PermissionRequest --adapter claude"
        in hooks["PermissionRequest"][0]["hooks"][0]["command"]
    )
    assert "SessionStart" in hooks
    assert any("observe" in entry["hooks"][0]["command"] for entry in hooks["PostToolUseFailure"])


def test_pending_observer_abstains_and_duplicate_events_keep_one_observation(tmp_path, hook):
    def notify_request():
        response = hook(tmp_path, "PermissionRequest")
        decision = json.loads(response.output) if response.output else {}
        assert "decision" not in decision
        assert "hookSpecificOutput" not in decision

    notify_request()
    for _ in range(2):
        resume = hook(tmp_path, "SessionStart", source="resume", tool_input={})
        assert "do not interrupt or resubmit" in resume.output
        notify_request()
    for _ in range(2):
        hook(tmp_path, "PostToolUse", tool_response={"exit_code": 0})
    assert len(status(tmp_path)["actions"]) == 1
    assert status(tmp_path)["actions"][0]["state"] == "completed"
