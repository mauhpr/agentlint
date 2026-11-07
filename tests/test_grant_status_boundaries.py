"""Public grant validation and compact status preserve narrow authorization."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from agentlint.activity import observe
from agentlint.approvals import active_grants, create_grant
from agentlint.cli import main


@pytest.mark.parametrize(
    "changes",
    [
        {"rule_id": None},
        {"rule_id": "other-rule"},
        {"finding_id": None},
        {"finding_id": "not-a-fingerprint"},
        {"file_path": None},
        {"file_path": "scope.py"},
        {"file_path": "missing"},
        {"file_path": "outside"},
    ],
)
def test_invalid_finding_scope_never_creates_a_grant(tmp_path, changes):
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "scope.py"
    source.write_text("public_value = 1\n")
    outside = tmp_path / "outside.py"
    outside.write_text("public_value = 2\n")
    options = {"rule_id": "no-secrets", "finding_id": "a" * 64, "file_path": str(source)}
    if changes.get("file_path") == "missing":
        changes = {"file_path": str(repository / "missing.py")}
    elif changes.get("file_path") == "outside":
        changes = {"file_path": str(outside)}
    options.update(changes)
    with pytest.raises(ValueError):
        create_grant(
            "secret-finding", repository=str(repository), reason="scope validation", **options
        )
    assert active_grants() == []


@pytest.mark.parametrize(
    "arguments,message",
    [
        (["--section", "activity"], "--section requires --json"),
        (["--conversation", "one", "--session-id", "two"], "must name the same session"),
    ],
)
def test_status_rejects_ambiguous_or_incomplete_filters(tmp_path, arguments, message):
    result = CliRunner().invoke(main, ["status", "--project-dir", str(tmp_path), *arguments])
    assert result.exit_code == 2
    assert message in result.output


def test_status_accepts_matching_conversation_aliases(tmp_path):
    result = CliRunner().invoke(
        main,
        [
            "status",
            "--project-dir",
            str(tmp_path),
            "--json",
            "--section",
            "activity",
            "--conversation",
            "one",
            "--session-id",
            "one",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload) == {"version", "project_dir", "scope", "activity"}
    assert payload["scope"]["session_id"] == "one"


def test_summary_separates_observed_request_and_past_policy_block(tmp_path):
    raw = {"session_id": "one", "tool_name": "Bash", "tool_input": {"command": "git status"}}
    observe({**raw, "tool_use_id": "waiting"}, event="PermissionRequest", project_dir=str(tmp_path))
    observe(
        {**raw, "tool_use_id": "blocked"},
        event="PreToolUse",
        project_dir=str(tmp_path),
        blocked_rules=("no-bash-file-write",),
    )
    result = CliRunner().invoke(main, ["status", "--summary", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Observed host requests: 1" in result.output
    assert "Past AgentLint blocks: 1" in result.output
    assert "awaiting_approval" in result.output
    assert "live state unconfirmed" in result.output
    assert "Details: agentlint status --history or --diagnostics" in result.output
