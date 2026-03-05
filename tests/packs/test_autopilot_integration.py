"""Integration tests: autopilot pack loaded via full load_rules pipeline."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs import load_rules


def test_autopilot_pack_has_eighteen_rules():
    rules = load_rules(["autopilot"])
    assert len(rules) == 18
    rule_ids = {r.id for r in rules}
    assert rule_ids == {
        "production-guard",
        "destructive-confirmation-gate",
        "dry-run-required",
        "bash-rate-limiter",
        "cross-account-guard",
        "operation-journal",
        "cloud-resource-deletion",
        "cloud-infra-mutation",
        "cloud-paid-resource-creation",
        "system-scheduler-guard",
        "network-firewall-guard",
        "docker-volume-guard",
        "ssh-destructive-command-guard",
        "remote-boot-partition-guard",
        "remote-chroot-guard",
        "package-manager-in-chroot",
        "subagent-safety-briefing",
        "subagent-transcript-audit",
    }


def test_production_guard_blocks_via_load_rules():
    """End-to-end: production-guard fires through load_rules path."""
    rules = load_rules(["autopilot"])
    pg = next(r for r in rules if r.id == "production-guard")
    ctx = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "psql -h prod-db.internal -d myapp -U admin"},
        project_dir="/tmp/project",
        config={},
    )
    violations = pg.evaluate(ctx)
    assert len(violations) == 1
    assert violations[0].severity == Severity.ERROR


def test_operation_journal_records_post_and_reports_stop():
    """End-to-end: journal records PostToolUse and reports at Stop."""
    rules = load_rules(["autopilot"])
    oj = next(r for r in rules if r.id == "operation-journal")
    state: dict = {}

    post_ctx = RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "gcloud projects list"},
        project_dir="/tmp/project",
        config={},
        session_state=state,
    )
    result = oj.evaluate(post_ctx)
    assert result == []

    stop_ctx = RuleContext(
        event=HookEvent.STOP,
        tool_name="",
        tool_input={},
        project_dir="/tmp/project",
        config={},
        session_state=state,
    )
    violations = oj.evaluate(stop_ctx)
    assert len(violations) == 1
    assert "1 operations" in violations[0].message


def test_destructive_gate_blocks_drop_database():
    rules = load_rules(["autopilot"])
    gate = next(r for r in rules if r.id == "destructive-confirmation-gate")
    ctx = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "psql -c 'DROP DATABASE production'"},
        project_dir="/tmp/project",
        config={},
        session_state={},
    )
    violations = gate.evaluate(ctx)
    assert len(violations) == 1
    assert violations[0].severity == Severity.ERROR


def test_cross_account_guard_warns_on_project_switch():
    rules = load_rules(["autopilot"])
    guard = next(r for r in rules if r.id == "cross-account-guard")
    state: dict = {}

    # First project — no warning
    ctx1 = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "gcloud --project=dev-project compute instances list"},
        project_dir="/tmp/project",
        config={},
        session_state=state,
    )
    assert guard.evaluate(ctx1) == []

    # Second different project — warning
    ctx2 = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "gcloud --project=prod-project compute instances list"},
        project_dir="/tmp/project",
        config={},
        session_state=state,
    )
    violations = guard.evaluate(ctx2)
    assert len(violations) == 1
    assert violations[0].severity == Severity.WARNING
