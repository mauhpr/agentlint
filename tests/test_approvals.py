"""Typed, expiring approvals."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

import agentlint.cli as cli
from agentlint.approvals import (
    active_grants,
    approvals_path,
    create_grant,
    matching_grant,
    parse_ttl,
    revoke_grant,
    self_approval_attempt,
)
from agentlint.config import AgentLintConfig
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs import load_rules


def _evaluate(project, command, *, required=(), tool="Bash", tool_input=None):
    config = AgentLintConfig(packs=["universal", "autopilot"], required_rules=list(required))
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool,
        tool_input=tool_input or {"command": command},
        project_dir=str(project),
    )
    return Engine(config, load_rules(config.packs)).evaluate(context)


def _sev(result, rule_id):
    return [v.severity for v in result.violations if v.rule_id == rule_id]


@pytest.mark.parametrize(("value", "minutes"), [("30m", 30), ("2h", 120), ("1d", 1440)])
def test_parse_ttl(value, minutes):
    assert parse_ttl(value) == timedelta(minutes=minutes)


@pytest.mark.parametrize("value", ["0m", "25h", "2d", "soon", "1w"])
def test_parse_ttl_rejects(value):
    with pytest.raises(ValueError):
        parse_ttl(value)


def test_grant_relaxes_only_its_own_class(tmp_path):
    cmd = "terraform destroy -auto-approve"
    assert Severity.ERROR in _sev(_evaluate(tmp_path, cmd), "destructive-confirmation-gate")
    # "PR merged" (git-merge) must not authorize other classes.
    create_grant("git-merge", repository=str(tmp_path), reason="PR #12 merged")
    assert Severity.ERROR in _sev(_evaluate(tmp_path, cmd), "destructive-confirmation-gate")
    assert matching_grant("token-budget", repository=str(tmp_path), command=None) is None
    create_grant("destructive-op", repository=str(tmp_path), reason="teardown of sandbox")
    result = _evaluate(tmp_path, cmd)
    gate = [v for v in result.violations if v.rule_id == "destructive-confirmation-gate"]
    assert gate and gate[0].severity == Severity.WARNING
    assert "allowed by approval apr_" in gate[0].message
    audit = [
        json.loads(x)
        for x in Path(os.environ["AGENTLINT_APPROVAL_AUDIT_FILE"]).read_text().splitlines()
    ]
    assert audit[-1]["action_class"] == "destructive-op"
    assert audit[-1]["rule_id"] == "destructive-confirmation-gate"


def test_model_spend_is_its_own_class(tmp_path):
    create_grant("model-spend", repository=str(tmp_path), reason="eval run")
    assert matching_grant("token-burn-against-team-budget", repository=str(tmp_path), command=None)
    assert (
        matching_grant("no-push-to-main", repository=str(tmp_path), command="git push origin main")
        is None
    )


def test_grant_is_bound_to_repository_and_operation(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    create_grant(
        "git-push-protected",
        repository=str(tmp_path),
        reason="hotfix",
        operation="git push origin main",
    )
    assert matching_grant(
        "no-push-to-main", repository=str(tmp_path), command="git push origin main"
    )
    assert not matching_grant(
        "no-push-to-main", repository=str(tmp_path), command="git push origin master"
    )
    assert not matching_grant(
        "no-push-to-main", repository=str(other), command="git push origin main"
    )
    assert not matching_grant("no-push-to-main", repository=str(tmp_path), command=None)


def test_expired_revoked_and_tampered_grants_are_ignored(tmp_path):
    past = datetime.now(UTC) - timedelta(hours=3)
    create_grant("cloud-delete", repository=str(tmp_path), reason="x", now=past)
    assert active_grants() == []
    live = create_grant("cloud-delete", repository=str(tmp_path), reason="x")
    assert [g["id"] for g in active_grants()] == [live["id"]]
    assert revoke_grant(live["id"]) and active_grants() == []
    assert not revoke_grant("apr_missing")
    now = datetime.now(UTC)
    forged = {
        "type": "grant",
        "id": "apr_forged",
        "action_class": "cloud-delete",
        "repository": str(tmp_path.resolve()),
        "operation": None,
        "reason": "x",
        "created_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(days=30)).isoformat(),
    }
    with approvals_path().open("a") as f:
        f.write(json.dumps(forged) + "\nnot json\n")
    assert active_grants() == []


def test_create_grant_validation(tmp_path):
    with pytest.raises(ValueError):
        create_grant("everything", repository=str(tmp_path), reason="x")
    with pytest.raises(ValueError):
        create_grant("git-merge", repository=str(tmp_path), reason=" ")
    with pytest.raises(ValueError):
        create_grant("git-merge", repository=str(tmp_path), reason="x", ttl=timedelta(days=2))
    with pytest.raises(ValueError):
        create_grant("git-merge", repository=str(tmp_path), reason="x", operation="a && b")


def test_required_rules_are_never_relaxed(tmp_path):
    create_grant("destructive-op", repository=str(tmp_path), reason="x")
    result = _evaluate(tmp_path, "rm -rf ~", required=["no-destructive-commands"])
    assert Severity.ERROR in _sev(result, "no-destructive-commands")


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        ("Bash", {"command": "agentlint approve grant model-spend --reason x"}),
        ("Bash", {"command": "uvx agentlint approve grant git-merge --reason ok"}),
        ("Bash", {"command": "echo '{}' >> ~/.cache/agentlint/approvals.jsonl"}),
        ("Write", {"file_path": "__APPROVALS__", "content": "{}"}),
    ],
)
def test_agents_cannot_self_approve(tmp_path, tool, tool_input):
    if tool_input.get("file_path") == "__APPROVALS__":
        tool_input = {**tool_input, "file_path": str(approvals_path())}
    result = _evaluate(tmp_path, None, tool=tool, tool_input=tool_input)
    assert Severity.ERROR in _sev(result, "approval-self-grant")


def test_listing_approvals_is_allowed():
    assert self_approval_attempt("Bash", {"command": "agentlint approve list"}) is None
    assert (
        self_approval_attempt("Bash", {"command": "cat ~/.cache/agentlint/approvals.jsonl"}) is None
    )
    assert self_approval_attempt("Read", {"file_path": ""}) is None


def test_cli_requires_interactive_terminal(tmp_path):
    result = CliRunner().invoke(
        cli.main, ["approve", "grant", "git-merge", "--reason", "x", "--project-dir", str(tmp_path)]
    )
    assert result.exit_code == 2 and "interactive terminal" in result.output
    assert active_grants() == []


def test_cli_grant_list_revoke(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_is_interactive", lambda: True)
    runner = CliRunner()
    bad = runner.invoke(cli.main, ["approve", "grant", "all", "--reason", "x"])
    assert bad.exit_code == 2 and "model-spend" in bad.output
    ttl = runner.invoke(
        cli.main, ["approve", "grant", "git-merge", "--reason", "x", "--ttl", "3d"], input="y\n"
    )
    assert ttl.exit_code == 2
    declined = runner.invoke(
        cli.main, ["approve", "grant", "git-merge", "--reason", "x"], input="n\n"
    )
    assert declined.exit_code == 1 and active_grants() == []
    ok = runner.invoke(
        cli.main,
        ["approve", "grant", "git-merge", "--reason", "PR merged", "--project-dir", str(tmp_path)],
        input="y\n",
    )
    assert ok.exit_code == 0, ok.output
    [grant] = active_grants()
    listed = runner.invoke(cli.main, ["approve", "list"]).output
    assert grant["id"] in listed and "git-merge" in listed
    assert (
        json.loads(runner.invoke(cli.main, ["approve", "list", "--json"]).output)[0]["id"]
        == grant["id"]
    )
    assert runner.invoke(cli.main, ["approve", "revoke", grant["id"]]).exit_code == 0
    assert runner.invoke(cli.main, ["approve", "list"]).output.strip() == "No active approvals."
    assert runner.invoke(cli.main, ["approve", "revoke", grant["id"]]).exit_code == 0
    assert runner.invoke(cli.main, ["approve", "revoke", "apr_nope"]).exit_code == 1
