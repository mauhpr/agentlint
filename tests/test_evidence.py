"""Evidence receipts: test recognition, exit status and reuse."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from agentlint.cli import main
from agentlint.evidence import (
    describe,
    exit_status,
    find_receipts,
    find_test_command,
    git_head,
    outcome,
    receipts_dir,
    write_receipt,
)


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest -q",
        "uv run pytest -q > /tmp/agentlint-tests.log 2>&1",
        "uv run --extra dev pytest tests/ 2>&1 | tee /tmp/log",
        "python -m pytest -x",
        "python3.12 -m pytest",
        "cd backend && poetry run pytest",
        "make test",
        "npm test",
        "pnpm run test:unit",
        "go test ./...",
        "cargo test",
        "npx vitest run",
        "env CI=1 pytest",
    ],
)
def test_recognized_test_runs(command):
    assert find_test_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "echo pytest",
        "printf 'run pytest later'",
        "grep pytest pyproject.toml",
        "make build",
        "ls tests",
    ],
)
def test_not_test_runs(command):
    assert find_test_command(command) is None


def test_unparseable_falls_back_to_legacy_heuristic():
    assert find_test_command("pytest $(git diff --name-only)")
    assert find_test_command("echo $(date)") is None


@pytest.mark.parametrize(
    ("response", "failed", "expected"),
    [
        ({"exit_code": 0}, False, "passed"),
        ({"exitCode": 1}, False, "failed"),
        ({"returncode": 2}, False, "failed"),
        ({"stdout": "ok"}, False, "completed"),
        (None, False, "completed"),
        ({"exit_code": True}, False, "completed"),
        ({"exit_code": 0}, True, "failed"),
    ],
)
def test_outcome(response, failed, expected):
    assert outcome(failed_event=failed, tool_response=response) == expected
    assert exit_status("nope") is None


def _git_repo(path: Path) -> str:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "x",
        ],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()


def test_git_head_matches_git(tmp_path):
    sha = _git_repo(tmp_path)
    assert git_head(str(tmp_path)) == sha
    subprocess.run(["git", "-C", str(tmp_path), "pack-refs", "--all"], check=True)
    assert git_head(str(tmp_path)) == sha
    assert git_head(str(tmp_path / "nope")) is None


def test_receipts_filter_by_repo_head_age_and_result(tmp_path):
    _git_repo(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    write_receipt("test-run", command="pytest", exit_code=0, repo=str(tmp_path))
    write_receipt("test-run", command="pytest -x", exit_code=1, repo=str(tmp_path))
    write_receipt("review", command="review PR 1", exit_code=None, repo=str(other))
    found = find_receipts(str(tmp_path))
    assert [r["command"] for r in found] == ["pytest"]
    assert describe(found[0]).startswith("local tests: `pytest` passed at ")
    # A new commit invalidates receipts bound to the old HEAD.
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "y",
        ],
        check=True,
    )
    assert find_receipts(str(tmp_path)) == []
    assert find_receipts(str(other), kind="review")[0]["kind"] == "review"
    assert find_receipts(str(other), max_age="1s", now=time.time() + 5) == []
    with pytest.raises(ValueError):
        write_receipt("guess", command="x", exit_code=0, repo=str(tmp_path))


def test_external_receipts_are_reused(tmp_path):
    ext = tmp_path / "ext"
    ext.mkdir()
    (ext / "r.json").write_text(
        json.dumps(
            {
                "v": 1,
                "kind": "deploy-verified",
                "command": "smoke prod",
                "exit_code": 0,
                "repo": str(tmp_path.resolve()),
                "created_at": datetime.now(UTC).isoformat(),
                "producer": "other-tool",
            }
        )
    )
    (ext / "bad.json").write_text("{nope")
    assert find_receipts(str(tmp_path)) == []
    [r] = find_receipts(str(tmp_path), extra_dirs=[str(ext)])
    assert r["producer"] == "other-tool"
    assert describe(r).startswith("verified deployment: `smoke prod` passed")


def _hook(tmp_path, event, command, response=None, adapter="codex"):
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(tmp_path)}
    if response is not None:
        payload["tool_response"] = response
    return CliRunner().invoke(
        main,
        ["check", "--adapter", adapter, "--event", event, "--project-dir", str(tmp_path)],
        input=json.dumps(payload),
    )


def test_hook_writes_receipt_for_redirected_uv_pytest(tmp_path):
    result = _hook(tmp_path, "PostToolUse", "uv run pytest -q > /tmp/t.log 2>&1", {"exit_code": 0})
    assert result.exit_code == 0, result.output
    [receipt] = [json.loads(p.read_text()) for p in receipts_dir().glob("*.json")]
    assert receipt["command"] == "uv run pytest -q > /tmp/t.log 2>&1"
    assert receipt["exit_code"] == 0 and receipt["repo"] == str(tmp_path.resolve())
    _hook(tmp_path, "PostToolUse", "uv run pytest -q", {"exit_code": 1})
    _hook(tmp_path, "PostToolUse", "echo pytest")
    assert len(list(receipts_dir().glob("*.json"))) == 1
    data = json.loads(
        CliRunner().invoke(main, ["evidence", "--json", "--project-dir", str(tmp_path)]).output
    )
    assert len(data["receipts"]) == 1
    text = CliRunner().invoke(main, ["evidence", "--project-dir", str(tmp_path)]).output
    assert "local tests" in text and "verified deployment  none" in text


def _drift_state(tmp_path, n=3):
    from agentlint.models import HookEvent, RuleContext
    from agentlint.packs.universal.drift_detector import DriftDetector

    rule = DriftDetector()
    state: dict = {}
    cfg = {"drift-detector": {"threshold": 1}}

    def ctx(event, tool, tool_input, response=None):
        return RuleContext(
            event=event,
            tool_name=tool,
            tool_input=tool_input,
            project_dir=str(tmp_path),
            session_state=state,
            config=cfg,
            tool_response=response,
        )

    for i in range(n):
        rule.evaluate(ctx(HookEvent.POST_TOOL_USE, "Edit", {"file_path": f"/x/f{i}.py"}))
    return rule, ctx, state


def test_drift_detector_counts_only_real_test_runs(tmp_path):
    from agentlint.models import HookEvent

    rule, ctx, state = _drift_state(tmp_path)
    rule.evaluate(ctx(HookEvent.POST_TOOL_USE, "Bash", {"command": "echo pytest"}))
    assert state["last_test_run"] is False
    rule.evaluate(
        ctx(HookEvent.POST_TOOL_USE, "Bash", {"command": "uv run pytest"}, {"exit_code": 1})
    )
    assert state["last_test_run"] is False
    rule.evaluate(ctx(HookEvent.POST_TOOL_USE, "Bash", {"command": "uv run pytest > log 2>&1"}))
    assert state["last_test_run"] is True and state["edited_files"] == []


def test_drift_detector_commit_check_reuses_fresh_receipts(tmp_path):
    from agentlint.models import HookEvent

    rule, ctx, state = _drift_state(tmp_path)
    commit = ctx(HookEvent.PRE_TOOL_USE, "Bash", {"command": "git commit -m x"})
    [warning] = rule.evaluate(commit)
    assert "No test evidence found" in warning.message
    state["_drift_warned_at_commit"] = False
    # Evidence written by another process after the edits satisfies the check.
    write_receipt("test-run", command="make test", exit_code=0, repo=str(tmp_path))
    assert rule.evaluate(commit) == []
    # New edits after that evidence bring the warning back, citing the older run.
    state["last_edit_ts"] = time.time() + 1
    [warning] = rule.evaluate(commit)
    assert (
        "Latest evidence predates these edits — local tests: `make test` passed" in warning.message
    )


def test_evidence_config_composes(tmp_path):
    from agentlint.config import load_config

    (tmp_path / "agentlint.yml").write_text("evidence:\n  receipts_dirs: [/r]\n  max_age: 2h\n")
    assert load_config(str(tmp_path)).evidence == {"receipts_dirs": ["/r"], "max_age": "2h"}
    assert os.environ["AGENTLINT_RECEIPTS_DIR"].endswith("receipts")
