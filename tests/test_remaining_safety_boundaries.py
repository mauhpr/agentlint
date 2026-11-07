"""Reject incomplete authorization and preserve conservative diagnostic fallbacks."""

from __future__ import annotations

import json
import shlex
import sqlite3
from contextlib import closing

import pytest
from click.testing import CliRunner

import agentlint.activity as activity
import agentlint.approvals as approvals
import agentlint.cli as cli
from agentlint.models import HookEvent, RuleContext
from agentlint.packs.security.no_bash_file_write import NoBashFileWrite
from agentlint.packs.universal.no_secrets import NoSecrets


def upload_command(source, header_option=""):
    return (
        f"curl --disable --request POST --upload-file {shlex.quote(str(source))} {header_option} "
        "'https://storage.googleapis.com/upload/storage/v1/b/private/o?uploadType=media&name=video.mp4&ifGenerationMatch=0'"
    )


@pytest.mark.parametrize("option", ["--header inline-value", "--other @/headers"])
def test_upload_rejects_non_file_or_unknown_header_options(tmp_path, option):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    with pytest.raises(ValueError, match="authentication must use"):
        approvals.create_grant(
            "cloud-upload",
            repository=str(tmp_path),
            reason="header boundary",
            operation=upload_command(source, option),
            max_bytes=100,
        )
    assert approvals.active_grants() == []


def test_header_growth_after_metadata_check_cannot_receive_a_grant(tmp_path, monkeypatch):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    headers = tmp_path / "headers"
    headers.write_text("Content-Type: video/mp4\n")
    metadata = headers.stat()
    original_fstat = approvals.os.fstat
    changed = False

    def fstat_then_grow(fd):
        nonlocal changed
        result = original_fstat(fd)
        if not changed and (result.st_dev, result.st_ino) == (metadata.st_dev, metadata.st_ino):
            changed = True
            headers.write_bytes(b"x" * 16385)
        return result

    monkeypatch.setattr(approvals.os, "fstat", fstat_then_grow)
    with pytest.raises(ValueError, match="header file exceeds its size limit"):
        approvals.create_grant(
            "cloud-upload",
            repository=str(tmp_path),
            reason="growing headers",
            operation=upload_command(source, f"--header @{headers}"),
            max_bytes=100,
        )
    assert changed
    assert approvals.active_grants() == []


def test_malformed_persisted_upload_scope_never_matches(tmp_path, monkeypatch):
    source = tmp_path / "video.mp4"
    source.write_bytes(b"video")
    command = upload_command(source)
    grant = approvals.create_grant(
        "cloud-upload",
        repository=str(tmp_path),
        reason="scope shape",
        operation=command,
        max_bytes=100,
    )
    grant["upload"] = None
    monkeypatch.setattr(approvals, "active_grants", lambda: [grant])
    assert (
        approvals.matching_grant("no-network-exfil", repository=str(tmp_path), command=command)
        is None
    )


@pytest.mark.parametrize("missing", ["file_path", "finding_id"])
def test_finding_match_requires_all_call_metadata(tmp_path, missing):
    source = tmp_path / "scope.py"
    source.write_text("public_value = 1\n")
    scope = {"file_path": str(source), "finding_id": "a" * 64}
    grant = approvals.create_grant(
        "secret-finding",
        repository=str(tmp_path),
        reason="exact finding",
        rule_id="no-secrets",
        **scope,
    )
    assert (
        approvals.matching_grant("no-secrets", repository=str(tmp_path), command=None, **scope)[
            "id"
        ]
        == grant["id"]
    )
    scope.pop(missing)
    assert (
        approvals.matching_grant("no-secrets", repository=str(tmp_path), command=None, **scope)
        is None
    )


def test_declined_finding_confirmation_shows_exact_scope_without_persisting(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "_is_interactive", lambda: True)
    source = tmp_path / "scope.py"
    fingerprint = "a" * 64
    result = CliRunner().invoke(
        cli.main,
        [
            "approve",
            "grant",
            "secret-finding",
            "--reason",
            "review scope",
            "--project-dir",
            str(tmp_path),
            "--file-path",
            str(source),
            "--finding-id",
            fingerprint,
            "--rule-id",
            "no-secrets",
        ],
        input="n\n",
    )
    assert result.exit_code == 1, result.output
    assert f"no-secrets finding {fingerprint} in {source}" in result.output
    assert approvals.active_grants() == []


def test_malformed_state_json_still_reports_a_redacted_finding():
    # Assemble synthetic detector markers without resembling a real fixture leak.
    content = json.dumps({"serial": 1})[:-1] + ', "' + "line" + 'age": "public-lineage",'
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        project_dir="/project",
        tool_input={"file_path": "state.json", "content": content},
    )
    findings = NoSecrets().evaluate(context)
    assert len(findings) == 1
    assert "Terraform state" in findings[0].message
    assert len(findings[0].finding_id) == 64
    assert "public-lineage" not in findings[0].message


def test_npm_placeholder_is_not_a_registry_credential():
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        project_dir="/project",
        tool_input={"file_path": ".npmrc", "content": "_auth" + "Token=placeholder"},
    )
    assert NoSecrets().evaluate(context) == []


@pytest.mark.parametrize("unsupported_first", [False, True])
def test_multiple_subprocess_calls_keep_each_call_classification(unsupported_first):
    first = "arguments" if unsupported_first else "['git', 'cat-file', '-e', 'HEAD']"
    code = f"import subprocess; subprocess.run({first}); subprocess.run(['git', 'cat-file', '-e', 'HEAD'])"
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        project_dir="/project",
        tool_input={"command": "python3 -c " + shlex.quote(code)},
    )
    findings = NoBashFileWrite().evaluate(context)
    assert bool(findings) is unsupported_first
    if unsupported_first:
        assert "Cannot classify" in findings[0].message


def test_unknown_storage_flags_remain_a_classification_block():
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        project_dir="/project",
        tool_input={"command": "gcloud storage cp /source gs://private/object --unknown"},
    )
    findings = NoBashFileWrite().evaluate(context)
    assert len(findings) == 1
    assert "Cannot classify cloud storage copy" in findings[0].message


def test_stale_pending_flag_on_policy_block_does_not_create_host_notice(tmp_path):
    activity.observe(
        {"session_id": "one", "tool_use_id": "blocked", "tool_name": "Bash"},
        event="PreToolUse",
        project_dir=str(tmp_path),
        blocked_rules=("no-bash-file-write",),
    )
    with closing(sqlite3.connect(activity._path())) as db, db:
        payload = json.loads(db.execute("SELECT payload FROM observations").fetchone()[0])
        assert payload["approval_seen"] is False
        db.execute("UPDATE observations SET pending=1")
    assert activity.pending_context(str(tmp_path), "one") is None
    assert activity.snapshot(str(tmp_path))["actions"][0]["state"] == "agentlint_blocked"
