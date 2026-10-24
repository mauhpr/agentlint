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
    "command",
    [
        "pytest -q | tail -20",
        "pytest -q 2>&1 | tee /tmp/tests.log",
        "pytest -q; echo done",
        "pytest -q || echo ignored",
    ],
)
def test_masked_shell_status_does_not_create_passing_test_evidence(tmp_path, command):
    _hook(tmp_path, "PostToolUse", command, {"exit_code": 0})
    assert list(receipts_dir().glob("*.json")) == []


@pytest.mark.parametrize(
    "command, reliable",
    [
        ("pytest -q", True),
        ("pytest -q > /tmp/test.log 2>&1", True),
        ("set -o pipefail && pytest -q | tail -20", True),
        ("set -euo pipefail && uv run pytest -q | tee /tmp/test.log", True),
        ("set -o pipefail && set +o pipefail && pytest | tail", False),
        ("set -o pipefail | cat && pytest | tail", False),
        ("set ignored pipefail && pytest | tail", False),
        ("pytest & wait", False),
        ("true || pytest", False),
        ("pytest $(git diff --name-only)", False),
        ("echo data | pytest", False),
        ("source options.sh && pytest", False),
        ("pytest && set +o pipefail && echo done", False),
        ("echo done", False),
        ("", False),
    ],
)
def test_test_status_proof_handles_shell_control_flow(command, reliable):
    from agentlint.evidence import test_result_is_reliable

    assert test_result_is_reliable(command) is reliable


def test_pipefail_test_log_produces_receipt(tmp_path):
    _hook(
        tmp_path, "PostToolUse", "set -o pipefail && pytest | tee /tmp/test.log", {"exit_code": 0}
    )
    [path] = receipts_dir().glob("*.json")
    assert json.loads(path.read_text())["exit_code"] == 0


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


def test_drift_does_not_cite_or_accept_another_sessions_test_run(tmp_path, monkeypatch):
    from agentlint.models import HookEvent

    monkeypatch.setenv("AGENTLINT_SESSION_ID", "other-session")
    write_receipt("test-run", command="pytest other_tests", exit_code=0, repo=str(tmp_path))
    monkeypatch.setenv("AGENTLINT_SESSION_ID", "current-session")
    rule, ctx, state = _drift_state(tmp_path)
    commit = ctx(HookEvent.PRE_TOOL_USE, "Bash", {"command": "git commit -m x"})
    [warning] = rule.evaluate(commit)
    assert "other_tests" not in warning.message
    assert "No test evidence found" in warning.message
    state["_drift_warned_at_commit"] = False
    write_receipt("test-run", command="pytest current_tests", exit_code=0, repo=str(tmp_path))
    assert rule.evaluate(commit) == []


def test_drift_state_is_partitioned_by_worktree(tmp_path):
    from dataclasses import replace

    from agentlint.models import HookEvent

    rule, ctx, state = _drift_state(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    other_context = replace(
        ctx(HookEvent.POST_TOOL_USE, "Edit", {"file_path": str(other / "app.py")}),
        project_dir=str(other),
    )
    assert rule.evaluate(other_context) == []
    assert state["edited_files"] == [str(other / "app.py")]
    # Returning to the first worktree restores its untested edits.
    commit = ctx(HookEvent.PRE_TOOL_USE, "Bash", {"command": "git commit -m x"})
    assert rule.evaluate(commit)


def test_absolute_patch_edits_and_shell_tests_use_the_same_actual_worktree(tmp_path):
    from agentlint.models import HookEvent, RuleContext
    from agentlint.packs.universal.drift_detector import DriftDetector

    worktree = tmp_path / "worktree"
    (worktree / ".git").mkdir(parents=True)
    state = {}

    def context(event, tool, payload, directory):
        return RuleContext(
            event=event,
            tool_name=tool,
            tool_input=payload,
            project_dir=str(tmp_path),
            working_directory=str(directory),
            session_state=state,
            config={"drift-detector": {"threshold": 1}},
            tool_response={"exit_code": 0},
        )

    rule = DriftDetector()
    for name in ("a.py", "b.py", "c.py"):
        rule.evaluate(
            context(HookEvent.POST_TOOL_USE, "Edit", {"file_path": str(worktree / name)}, tmp_path)
        )
    commit = context(HookEvent.PRE_TOOL_USE, "Bash", {"command": "git commit -m change"}, worktree)
    assert rule.evaluate(commit), "The real worktree must retain its untested absolute-path edits"
    rule.evaluate(context(HookEvent.POST_TOOL_USE, "Bash", {"command": "pytest -q"}, worktree))
    assert rule.evaluate(commit) == []


def test_saving_json_evidence_does_not_invalidate_tests_of_unchanged_code(tmp_path):
    from agentlint.models import HookEvent

    rule, ctx, state = _drift_state(tmp_path)
    write_receipt("test-run", command="pytest -q", exit_code=0, repo=str(tmp_path))
    last_code_edit = state["last_edit_ts"]
    rule.evaluate(
        ctx(HookEvent.POST_TOOL_USE, "Write", {"file_path": str(tmp_path / "receipt.json")})
    )
    assert state["last_edit_ts"] == last_code_edit
    commit = ctx(HookEvent.PRE_TOOL_USE, "Bash", {"command": "git commit -m change"})
    assert rule.evaluate(commit) == []
