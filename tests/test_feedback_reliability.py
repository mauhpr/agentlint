"""Regressions for protocol, privacy, read-only inspection and scoped grants."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from agentlint.agentchute.policy import DeclarativePolicyRule, policy_diagnostics
from agentlint.config import AgentLintConfig
from agentlint.diagnostics import validate_codex_output, write_bundle
from agentlint.engine import Engine
from agentlint.exceptions import applies, validate_exceptions
from agentlint.formats.codex_hooks import CodexHookFormatter
from agentlint.models import AgentEvent, HookEvent, RuleContext, Severity, Violation
from agentlint.packs import load_rules
from agentlint.recorder import summarize_tool_input
from agentlint.utils.shell import (
    is_readonly_cloud_command,
    is_readonly_psql_command,
    mutation_command,
)


def _result(command: str, project_dir: str):
    config = AgentLintConfig(packs=["universal", "security", "autopilot"])
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir=project_dir,
    )
    return Engine(config, load_rules(config.packs)).evaluate(context)


def test_wrapped_reads_and_quoted_examples(tmp_path):
    cloud = "env FOO=bar gcloud compute instances describe vm --project prod-main"
    assert is_readonly_cloud_command(cloud)
    assert not any(
        v.rule_id == "production-guard" for v in _result(cloud, str(tmp_path)).violations
    )
    example = "env FOO=bar printf '%s' 'gcloud projects delete prod-main'"
    assert mutation_command(example) == "printf"
    assert not _result(example, str(tmp_path)).is_blocking
    assert not is_readonly_cloud_command("env FOO=$(bad) gcloud projects list --project prod-main")
    assert not is_readonly_cloud_command(
        "gcloud projects list delete prod-main --project prod-main"
    )


def test_explicit_readonly_sql_and_file(tmp_path):
    sql = "BEGIN READ ONLY; SELECT 1; COMMIT;"
    inline = f"psql -h prod-db.internal -c '{sql}'"
    assert is_readonly_psql_command(inline, str(tmp_path))
    assert not any(
        v.rule_id == "production-guard" for v in _result(inline, str(tmp_path)).violations
    )
    (tmp_path / "inspect.sql").write_text(sql)
    file_command = "env FOO=bar psql -h prod-db.internal -f inspect.sql"
    assert is_readonly_psql_command(file_command, str(tmp_path))
    assert not any(
        v.rule_id == "production-guard" for v in _result(file_command, str(tmp_path)).violations
    )
    (tmp_path / "inspect.sql").write_text("BEGIN READ ONLY; DELETE FROM users; COMMIT;")
    assert not is_readonly_psql_command(file_command, str(tmp_path))
    assert not is_readonly_psql_command("psql -h prod-db.internal -c 'SELECT 1'", str(tmp_path))


def test_recording_never_retains_bearer_or_prompt():
    command = "curl -H 'Authorization: Bearer TEST_SECRET_SENTINEL' https://example.test"
    summary = summarize_tool_input("Bash", {"command": command})
    assert summary["command"] == "curl [arguments redacted]"
    assert "TEST_SECRET_SENTINEL" not in json.dumps(summary)
    prompt = summarize_tool_input("UserPromptSubmit", {}, "TEST_SECRET_SENTINEL")
    assert "TEST_SECRET_SENTINEL" not in json.dumps(prompt)


def test_codex_posttool_error_protocol_and_sanitized_bundle(tmp_path):
    bundle = tmp_path / "diagnostic.json"
    payload = {
        "tool_name": "apply_patch",
        "tool_input": {"command": "not a patch", "secret_value": "TEST_SECRET_SENTINEL"},
        "cwd": str(tmp_path),
    }
    env = {
        **os.environ,
        "AGENTLINT_SESSION_DIR": str(tmp_path / "sessions"),
        "AGENTLINT_AGENTCHUTE_POLICY_DIR": str(tmp_path / "policy"),
    }
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentlint",
            "check",
            "--event",
            "PostToolUse",
            "--adapter",
            "codex",
            "--project-dir",
            str(tmp_path),
            "--diagnostic-bundle",
            str(bundle),
        ],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert process.returncode == 0
    assert not process.stderr
    output = json.loads(process.stdout)
    assert output["decision"] == "block"
    assert output["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "codex-patch-inspection" in output["reason"]
    diagnostic = json.loads(bundle.read_text())
    assert diagnostic["output_validation"]["valid"] is True
    assert diagnostic["adapter"] == "codex"
    assert isinstance(diagnostic["rule_ids_evaluated"], list)
    assert "TEST_SECRET_SENTINEL" not in bundle.read_text()
    assert "not a patch" not in bundle.read_text()


@pytest.mark.parametrize(("mode", "blocked"), [("standard", False), ("strict", True)])
def test_codex_token_budget_obeys_effective_severity_at_cli_boundary(tmp_path, mode, blocked):
    (tmp_path / "agentlint.yml").write_text(f"severity: {mode}\npacks: [universal]\n")
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    (sessions / "warning-test.json").write_text(
        json.dumps({"token_budget": {"tool_invocations": {"Bash": 159}}})
    )
    env = {
        **os.environ,
        "AGENTLINT_CACHE_DIR": str(sessions),
        "AGENTLINT_SESSION_ID": "warning-test",
    }
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentlint",
            "check",
            "--event",
            "PostToolUse",
            "--adapter",
            "codex",
            "--project-dir",
            str(tmp_path),
        ],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}}),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    assert process.returncode == 0
    assert not process.stderr
    output = json.loads(process.stdout)
    if blocked:
        assert output["decision"] == "block"
        assert "token-budget" in output["reason"]
    else:
        assert "decision" not in output
        assert "reason" not in output
    context = output["hookSpecificOutput"]
    assert context["hookEventName"] == "PostToolUse"
    assert "[token-budget] Session activity: 160/200" in context["additionalContext"]


@pytest.mark.parametrize(
    "event",
    [AgentEvent.POST_TOOL_USE, AgentEvent.POST_TOOL_FAILURE, "PostToolUse", "PostToolUseFailure"],
)
@pytest.mark.parametrize("severity", [Severity.WARNING, Severity.INFO])
def test_codex_posttool_advisories_never_block(event, severity):
    formatter = CodexHookFormatter()
    violations = [Violation("advisory", "Keep working", severity)]
    output = json.loads(formatter.format(violations, event))
    assert formatter.exit_code(violations, event) == 0
    assert "decision" not in output
    assert "reason" not in output
    assert "Keep working" in output["hookSpecificOutput"]["additionalContext"]


def test_codex_mixed_posttool_violations_block_only_for_errors():
    violations = [
        Violation("error", "Unsafe action", Severity.ERROR),
        Violation("warning", "Budget advisory", Severity.WARNING),
    ]
    output = json.loads(CodexHookFormatter().format(violations, "PostToolUse"))
    assert output["decision"] == "block"
    assert "Unsafe action" in output["reason"]
    assert "Budget advisory" not in output["reason"]
    assert "Budget advisory" in output["hookSpecificOutput"]["additionalContext"]


@pytest.mark.parametrize(
    ("output", "event", "exit_code", "blocked", "valid"),
    [
        (None, "PostToolUse", 0, False, True),
        (None, "PostToolUse", 0, True, False),
        ("not json", "PostToolUse", 0, True, False),
        ("[]", "PostToolUse", 0, True, False),
        ('{"decision":"block","reason":"why"}', "PostToolUse", 2, True, False),
        (
            '{"hookSpecificOutput":{"hookEventName":"post_tool_use"}}',
            "PostToolUse",
            0,
            False,
            False,
        ),
        ('{"hookSpecificOutput":{"hookEventName":"PreToolUse"}}', "PreToolUse", 0, True, False),
        ('{"decision":"block"}', "PostToolUse", 0, True, False),
        (
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny"}}',
            "PreToolUse",
            0,
            True,
            True,
        ),
        ('{"decision":"block","reason":"why"}', "PostToolUse", 0, True, True),
        ('{"decision":"block","reason":"why"}', "PostToolUse", 0, False, False),
        ('{"continue":false}', "SessionStart", 0, False, False),
        (
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny"}}',
            "PreToolUse",
            0,
            False,
            False,
        ),
        ('{"hookSpecificOutput":{"hookEventName":"SessionStart"}}', "SessionStart", 0, True, False),
        (
            '{"continue":false,"hookSpecificOutput":{"hookEventName":"SessionStart"}}',
            "SessionStart",
            0,
            True,
            True,
        ),
    ],
)
def test_codex_output_validation_paths(output, event, exit_code, blocked, valid):
    assert (
        validate_codex_output(output, event=event, exit_code=exit_code, blocked=blocked)["valid"]
        is valid
    )


def test_codex_formatter_covers_prompt_and_session_paths():
    formatter = CodexHookFormatter()
    error = Violation("rule", "blocked", Severity.ERROR, suggestion="Use a safe command")
    warning = Violation("warning", "review", Severity.WARNING)
    assert formatter.exit_code([error], "UserPromptSubmit") == 0
    assert formatter.format([], "UserPromptSubmit") is None
    prompt = json.loads(formatter.format([error], "UserPromptSubmit"))
    assert prompt["decision"] == "block"
    assert prompt["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    advisory = json.loads(formatter.format([warning], "UserPromptSubmit"))
    assert "decision" not in advisory
    session = json.loads(formatter.format([error], "SessionStart"))
    assert session["continue"] is False
    assert session["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "continue" not in json.loads(formatter.format([warning], "SessionStart"))


def test_bundle_uses_only_minimized_fields(tmp_path):
    destination = tmp_path / "bundle.json"
    write_bundle(
        str(destination),
        raw={
            "tool_name": "Bash",
            "tool_input": {
                "command": "curl -H 'Authorization: Bearer TEST_SECRET_SENTINEL' https://example.test",
                "secret_name": "TEST_SECRET_SENTINEL",
            },
        },
        event="PreToolUse",
        adapter="codex",
        version="2.7.0",
        project_dir="/private/TEST_SECRET_SENTINEL",
        rules_evaluated=1,
        rule_ids_evaluated=["no-secrets"],
        violations=[Violation("no-secrets", "secret TEST_SECRET_SENTINEL", Severity.ERROR)],
        validation={"valid": True, "reason": "Codex JSON protocol"},
    )
    bundle = json.loads(destination.read_text())
    assert bundle["command_summary"] == "curl [arguments redacted]"
    assert bundle["other_input_keys"] == 1
    assert bundle["rule_ids_evaluated"] == ["no-secrets"]
    assert "TEST_SECRET_SENTINEL" not in destination.read_text()


def test_cached_policy_block_explains_match_source_and_correction(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTLINT_AGENTCHUTE_POLICY_DIR", str(tmp_path))
    (tmp_path / "policy.json").write_text(
        json.dumps(
            {
                "version": 4,
                "rules": [
                    {
                        "id": "org-check",
                        "severity": "error",
                        "locked": True,
                        "message": "Blocked by workspace policy",
                        "match": {
                            "field": "command",
                            "operator": "contains",
                            "value": "terraform destroy",
                        },
                    }
                ],
            }
        )
    )
    rule = DeclarativePolicyRule(json.loads((tmp_path / "policy.json").read_text())["rules"][0])
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "terraform destroy"},
        project_dir=str(tmp_path),
    )
    violation = Engine(AgentLintConfig(packs=["universal"]), [rule]).evaluate(context).violations[0]
    assert violation.rule_id == "org-check"
    assert "Matched command contains" in violation.message
    assert "terraform destroy" in violation.operation
    assert "policy.json" in violation.policy_source
    assert "policy explain" in violation.suggestion
    diagnostics = policy_diagnostics()
    assert diagnostics["cached_rules_enforced"] is True
    assert diagnostics["connection"] == "not checked"
    assert diagnostics["restart_for_policy_cache"] is False


def test_online_policy_probe_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTLINT_AGENTCHUTE_POLICY_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "TEST_SECRET_SENTINEL")
    calls = []

    class Response:
        status_code = 200

    def get(url, headers, timeout):
        calls.append((url, headers, timeout))
        return Response()

    monkeypatch.setattr("requests.get", get)
    diagnostic = policy_diagnostics(online=True)
    assert diagnostic["connection"] == "connected"
    assert len(calls) == 1
    assert not (tmp_path / "policy.json").exists()
    assert "TEST_SECRET_SENTINEL" not in json.dumps(diagnostic)


def test_exact_short_lived_exception_is_audited_and_locked_rules_still_block(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    command = "git push --force origin main"
    grant = {
        "id": "ticket-123",
        "rule_id": "no-force-push",
        "repository": str(tmp_path),
        "operation": command,
        "created_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "reason": "approved maintenance",
    }
    validate_exceptions([grant])
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setenv("AGENTLINT_EXCEPTION_AUDIT_FILE", str(audit))
    config = AgentLintConfig(packs=["universal"], exceptions=[grant])
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir=str(tmp_path),
    )
    result = Engine(config, load_rules(config.packs)).evaluate(context)
    assert not any(v.rule_id == "no-force-push" for v in result.violations)
    assert json.loads(audit.read_text().splitlines()[0])["exception_id"] == "ticket-123"
    assert command not in audit.read_text()
    monkeypatch.setenv("AGENTLINT_EXCEPTION_AUDIT_FILE", str(tmp_path))
    assert any(
        v.rule_id == "no-force-push"
        for v in Engine(config, load_rules(config.packs)).evaluate(context).violations
    )
    monkeypatch.setenv("AGENTLINT_EXCEPTION_AUDIT_FILE", str(audit))
    changed = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "git push --force origin other"},
        project_dir=str(tmp_path),
    )
    assert any(
        v.rule_id == "no-force-push"
        for v in Engine(config, load_rules(config.packs)).evaluate(changed).violations
    )
    config.required_rules = ["no-force-push"]
    assert any(
        v.rule_id == "no-force-push"
        for v in Engine(config, load_rules(config.packs)).evaluate(context).violations
    )
    expired = {**grant, "expires_at": (now - timedelta(seconds=1)).isoformat()}
    assert any(
        v.rule_id == "no-force-push"
        for v in Engine(
            AgentLintConfig(packs=["universal"], exceptions=[expired]), load_rules(["universal"])
        )
        .evaluate(context)
        .violations
    )
    too_long = {**grant, "expires_at": (now + timedelta(days=8)).isoformat()}
    with pytest.raises(ValueError):
        validate_exceptions([too_long])


def test_exception_schema_rejects_broad_and_ambiguous_grants(tmp_path):
    now = datetime.now(UTC)
    base = {
        "id": "ticket-1",
        "rule_id": "no-force-push",
        "repository": str(tmp_path),
        "operation": "git push --force origin main",
        "created_at": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": (now + timedelta(hours=1)).isoformat(),
        "reason": "maintenance",
    }
    assert validate_exceptions(None) == []
    cases = [
        "not a list",
        ["not a mapping"],
        [{**base, "id": "bad id"}],
        [base, base],
        [{**base, "repository": "relative/repo"}],
        [{**base, "operation": "git push; rm -rf /"}],
        [{**base, "operation": "bash -c 'git push --force origin main'"}],
        [{**base, "created_at": now.replace(tzinfo=None).isoformat()}],
        [{**base, "expires_at": base["created_at"]}],
        [{**base, "reason": ""}],
    ]
    for grants in cases:
        with pytest.raises(ValueError):
            validate_exceptions(grants)
    assert applies(
        base,
        rule_id="no-force-push",
        repository=str(tmp_path),
        command="git push --force origin main",
    )
    assert not applies(
        base, rule_id="another", repository=str(tmp_path), command="git push --force origin main"
    )
    assert not applies(
        base,
        rule_id="no-force-push",
        repository=str(tmp_path / "other"),
        command="git push --force origin main",
    )


def test_readonly_sql_rejects_unsafe_file_shapes(tmp_path):
    command = "psql -h prod-db.internal -f inspect.sql"
    assert not is_readonly_psql_command(command, str(tmp_path))
    (tmp_path / "inspect.sql").write_text("BEGIN READ ONLY; SELECT 1; COMMIT; -- comment")
    assert not is_readonly_psql_command(command, str(tmp_path))
    (tmp_path / "inspect.sql").write_text("BEGIN READ ONLY; SELECT 1; COMMIT;" + " " * 65536)
    assert not is_readonly_psql_command(command, str(tmp_path))
    (tmp_path / "inspect.sql").write_text("BEGIN READ ONLY; SELECT 1; COMMIT;")
    assert not is_readonly_psql_command("psql -h prod-db.internal -f ../inspect.sql", str(tmp_path))
    assert not is_readonly_psql_command(
        "psql -h prod-db.internal -c 'BEGIN READ ONLY; SELECT 1 INTO x; COMMIT;'", str(tmp_path)
    )
