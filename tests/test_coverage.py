"""Coverage truth: user-scope hooks, wrappers, heartbeats and effective policy."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from agentlint.cli import main
from agentlint.config import AgentLintConfig
from agentlint.coverage import (
    format_age,
    inspect_hook_file,
    platform_coverage,
    read_heartbeat,
    record_heartbeat,
)
from agentlint.formats.plain_json import PlainJsonFormatter
from agentlint.models import Severity, Violation


def _codex_hooks(command: str) -> dict:
    entry = {"matcher": "^(Bash|apply_patch)$", "hooks": [{"type": "command", "command": command}]}
    return {"hooks": {"PreToolUse": [entry], "PostToolUse": [entry]}}


def _write(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


@pytest.fixture
def home() -> Path:
    return Path(os.environ["HOME"])


def test_user_scope_codex_install_is_not_missing(tmp_path, home):
    _write(
        home / ".codex" / "hooks.json",
        _codex_hooks("agentlint check --event PreToolUse --adapter codex"),
    )
    cov = platform_coverage("codex", str(tmp_path))
    assert cov.state == "installed"
    assert cov.configured.scope == "user"
    assert cov.configured.events == ["PostToolUse", "PreToolUse"]


def test_project_scope_wins_over_user_scope(tmp_path, home):
    _write(home / ".codex" / "hooks.json", _codex_hooks("agentlint check --event PreToolUse"))
    _write(
        tmp_path / ".codex" / "hooks.json", _codex_hooks("/old/agentlint check --event PreToolUse")
    )
    cov = platform_coverage("codex", str(tmp_path), resolved_command="/new/agentlint")
    assert (cov.configured.scope, cov.state) == ("project", "stale")


def test_delegating_wrapper_is_recognized(tmp_path):
    path = _write(
        tmp_path / "hooks.json",
        _codex_hooks("/opt/venv/bin/python /work/.agentlint/codex_hook.py PreToolUse"),
    )
    install = inspect_hook_file(path)
    assert install.state == "wrapper"
    assert install.events == ["PostToolUse", "PreToolUse"]


def test_custom_and_missing_and_non_json(tmp_path):
    assert inspect_hook_file(tmp_path / "absent.json").state == "missing"
    other = _write(tmp_path / "other.json", {"hooks": {"PreToolUse": [{"command": "lint"}]}})
    assert inspect_hook_file(other).state == "custom"
    toml = tmp_path / "config.toml"
    toml.write_text('[[hooks]]\ncommand = "agentlint check --event PreToolUse"\n')
    assert inspect_hook_file(toml).state == "installed"


def test_heartbeat_roundtrip_has_no_content(tmp_path):
    record_heartbeat(
        "codex", event="PreToolUse", tool="rm -rf /secret", project_dir=str(tmp_path), version="x"
    )
    beat = read_heartbeat("codex")
    assert beat["tool"] == "[other]"
    assert str(tmp_path) not in json.dumps(beat)
    assert read_heartbeat("claude") is None


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (None, "never observed"),
        (5, "5s ago"),
        (600, "10m ago"),
        (7200, "2h ago"),
        (259200, "3d ago"),
    ],
)
def test_format_age(seconds, text):
    assert format_age(seconds) == text


def test_check_records_heartbeat_and_status_reports_observed(tmp_path, home):
    _write(
        home / ".codex" / "hooks.json",
        _codex_hooks("agentlint check --event PreToolUse --adapter codex"),
    )
    runner = CliRunner()
    before = runner.invoke(main, ["status", "--project-dir", str(tmp_path), "--json"])
    assert json.loads(before.output)["agents"]["codex"]["last_seen"] is None
    result = runner.invoke(
        main,
        ["check", "--adapter", "codex", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
        input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": str(tmp_path)}
        ),
    )
    assert result.exit_code == 0, result.output
    data = json.loads(
        runner.invoke(main, ["status", "--project-dir", str(tmp_path), "--json"]).output
    )
    codex = data["agents"]["codex"]
    assert codex["state"] == "installed" and codex["scope"] == "user"
    assert codex["last_seen"]["event"] == "PreToolUse"
    assert codex["last_seen_age_seconds"] < 60
    text = runner.invoke(main, ["status", "--project-dir", str(tmp_path)]).output
    assert "observed: " in text and "this project" in text
    assert "/hooks review" in text


def test_doctor_fix_does_not_duplicate_user_scope_hooks(tmp_path, home, monkeypatch):
    monkeypatch.setenv("CODEX_PROJECT_DIR", str(tmp_path))
    _write(home / ".codex" / "hooks.json", _codex_hooks("/w/.agentlint/codex_hook.py"))
    (home / ".codex" / "config.toml").write_text("[features]\nhooks = true\n")
    (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
    result = CliRunner().invoke(main, ["doctor", "--fix", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert not (tmp_path / ".codex" / "hooks.json").exists()
    assert "delegates to an AgentLint wrapper" in result.output
    assert "never observed" in result.output


def test_status_json_effective_policy_layers(tmp_path, monkeypatch):
    ws = tmp_path / "agentlint.yml"
    ws.write_text("workspace:\n  required_rules: [no-secrets]\npacks: [universal]\n")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "agentlint.yml").write_text(
        "packs: [universal]\nrules:\n  no-large-diff:\n    max_lines: 500\n"
    )
    monkeypatch.setenv("AGENTLINT_WORKSPACE_CONFIG", str(ws))
    data = json.loads(
        CliRunner().invoke(main, ["status", "--project-dir", str(repo), "--json"]).output
    )
    policy = data["policy"]
    assert [layer["kind"] for layer in policy["layers"]] == ["workspace", "repository"]
    assert policy["required_rules"] == ["no-secrets"]
    assert policy["rule_origins"]["no-large-diff"] == str(repo / "agentlint.yml")
    assert policy["packs_source"] == "explicit"


def test_describe_policy_source_layers():
    cfg = AgentLintConfig(
        layers=[
            {"kind": "workspace", "path": "/w/agentlint.yml"},
            {"kind": "repository", "path": "/w/r/agentlint.yml"},
        ],
        rule_origins={"no-large-diff": "/w/r/agentlint.yml"},
        required_rules=["no-secrets"],
    )
    assert cfg.describe_policy_source("no-secrets", "universal", builtin=True) == (
        "built-in universal pack; required by workspace policy /w/agentlint.yml"
    )
    assert "configured in /w/r/agentlint.yml" in cfg.describe_policy_source(
        "no-large-diff", "quality", builtin=True
    )
    assert (
        "default settings (policy files: /w/agentlint.yml, /w/r/agentlint.yml)"
        in cfg.describe_policy_source("no-force-push", "universal", builtin=True)
    )
    assert AgentLintConfig().describe_policy_source("x", "mine", builtin=False) == (
        "custom pack 'mine'; built-in defaults (no policy file)"
    )


def test_engine_denial_names_layer(tmp_path):
    (tmp_path / "agentlint.yml").write_text("packs: [universal]\n")
    result = CliRunner().invoke(
        main,
        ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
        input=json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}}
        ),
    )
    reason = json.loads(result.output)["hookSpecificOutput"]["permissionDecisionReason"]
    assert f"default settings (policy files: {tmp_path / 'agentlint.yml'})" in reason


def test_formatter_shows_file_and_line():
    v = Violation(rule_id="r", message="m", severity=Severity.ERROR, file_path="a.py", line=3)
    lines = PlainJsonFormatter()._format_violation_lines(
        [v, Violation(rule_id="s", message="n", severity=Severity.ERROR, file_path="b.py")]
    )
    assert "  File: a.py:3" in lines and "  File: b.py" in lines


def test_degraded_cloud_is_unmistakable_in_status_and_doctor(tmp_path, monkeypatch):
    import time

    from agentlint.agentchute import queue

    monkeypatch.setenv("AGENTCHUTE_ENABLED", "true")
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_x")
    qdir = Path(os.environ["AGENTLINT_AGENTCHUTE_QUEUE_DIR"])
    qdir.mkdir(parents=True)
    old = time.time() - 3 * 86400
    (qdir / "queue.jsonl").write_text(
        "".join(
            json.dumps({"event_id": str(i), "queued_at": old + i, "event": {}}) + "\n"
            for i in range(5)
        )
    )
    queue._record_failure(outcome="rate_limited", http_status=429, retry_after=900)
    ws = tmp_path / "agentlint.yml"
    ws.write_text("workspace:\n  required_rules: [no-secrets]\npacks: [universal]\n")
    monkeypatch.setenv("AGENTLINT_WORKSPACE_CONFIG", str(ws))

    from agentlint.agentchute.policy import PolicyRefreshResult

    refresh = []

    def fake_refresh():
        refresh.append(1)
        return PolicyRefreshResult(ok=False, error="HTTP 429")

    monkeypatch.setattr("agentlint.agentchute.policy.refresh_policy", fake_refresh)
    out = CliRunner().invoke(main, ["status", "--project-dir", str(tmp_path)]).output
    assert "AgentChute: degraded" in out
    assert "Events queued: 5 pending / 5 total, oldest 3d old" in out
    assert "next attempt in 1" in out  # ~15m
    assert "delivery failing (rate_limited, HTTP 429)" in out
    assert "no cached organization policy" in out
    assert "Still enforced locally:" in out
    assert "required workspace rules: no-secrets" in out
    assert f"Workspace: AGENTLINT_WORKSPACE_CONFIG={ws}" in out
    assert f"Workspace layer: {ws}" in out

    doc = CliRunner().invoke(main, ["doctor", "--project-dir", str(tmp_path)]).output
    assert "!!  AgentChute: degraded (5 pending, oldest 3d" in doc
    assert "Still enforced locally:" in doc
    assert refresh == []  # doctor is read-only without --online/--fix
    online = CliRunner().invoke(main, ["doctor", "--online", "--project-dir", str(tmp_path)])
    assert online.exit_code == 0, online.output
    assert refresh == [1]
    assert "Cloud policy: HTTP 429" in online.output


def test_check_patch_reports_config_errors(tmp_path):
    (tmp_path / "agentlint.yml").write_text("- not a mapping\n")
    result = CliRunner().invoke(
        main, ["check-patch", "--project-dir", str(tmp_path), "-"], input="x"
    )
    assert result.exit_code == 2
    assert "configuration error" in result.output


def test_disabled_cloud_backlog_is_a_note_not_degraded(tmp_path, monkeypatch):
    from agentlint.agentchute import queue

    qdir = Path(os.environ["AGENTLINT_AGENTCHUTE_QUEUE_DIR"])
    qdir.mkdir(parents=True)
    (qdir / "queue.jsonl").write_text(
        json.dumps({"event_id": "1", "queued_at": 1.0, "event": {}}) + "\n"
    )
    queue._record_failure(outcome="rate_limited", http_status=429)
    out = CliRunner().invoke(main, ["status", "--project-dir", str(tmp_path)]).output
    assert "AgentChute: off" in out
    assert "degraded" not in out and "consecutive failure" not in out
    assert "1 undelivered event(s) remain" in out and "not being sent" in out
    doc = CliRunner().invoke(main, ["doctor", "--project-dir", str(tmp_path)]).output
    assert "..  AgentChute: 1 undelivered event(s) remain" in doc


def test_status_next_step_for_unobserved_hooks(tmp_path, home, monkeypatch):
    monkeypatch.setenv("CODEX_PROJECT_DIR", str(tmp_path))
    _write(home / ".codex" / "hooks.json", _codex_hooks("agentlint check --event PreToolUse"))
    (tmp_path / "agentlint.yml").write_text("packs: [universal]\n")
    out = CliRunner().invoke(main, ["status", "--project-dir", str(tmp_path)]).output
    assert "Next: hooks for codex are configured but not yet observed" in out
