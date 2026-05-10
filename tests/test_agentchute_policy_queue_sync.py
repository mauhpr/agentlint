from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from agentlint.models import HookEvent, RuleContext, Severity


def test_policy_refresh_writes_cache_and_etag(tmp_path, monkeypatch):
    from agentlint.agentchute import policy

    monkeypatch.setenv("AGENTLINT_AGENTCHUTE_POLICY_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_x")
    monkeypatch.setenv("AGENTCHUTE_API_URL", "https://api.example.test/v1")

    body = {
        "version": 7,
        "updated_at": "2026-05-10T00:00:00Z",
        "rules": [
            {
                "id": "block-rm",
                "event": "PreToolUse",
                "severity": "error",
                "match": {"field": "command", "operator": "command_verb", "value": "rm"},
            }
        ],
        "required_packs": [{"name": "agentlint"}],
    }
    response = MagicMock(status_code=200, content=b"x", headers={"ETag": "p7"})
    response.json.return_value = body

    with patch("requests.get", return_value=response) as mock_get:
        result = policy.refresh_policy()

    assert result.ok is True
    assert result.version == 7
    assert json.loads((tmp_path / "policy.json").read_text())["version"] == 7
    meta = json.loads((tmp_path / "policy-meta.json").read_text())
    assert meta["etag"] == "p7"
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer ac_team_test_x"


def test_policy_refresh_handles_304_with_cached_policy(tmp_path, monkeypatch):
    from agentlint.agentchute import policy

    monkeypatch.setenv("AGENTLINT_AGENTCHUTE_POLICY_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_x")
    (tmp_path / "policy.json").write_text(
        json.dumps({"version": 3, "rules": []}), encoding="utf-8"
    )
    (tmp_path / "policy-meta.json").write_text(
        json.dumps({"etag": "old"}), encoding="utf-8"
    )
    response = MagicMock(status_code=304, content=b"", headers={})

    with patch("requests.get", return_value=response) as mock_get:
        result = policy.refresh_policy()

    assert result.ok is True
    assert result.version == 3
    assert mock_get.call_args.kwargs["headers"]["If-None-Match"] == "old"


def test_policy_refresh_reports_invalid_and_oversized_payload(tmp_path, monkeypatch):
    from agentlint.agentchute import policy

    monkeypatch.setenv("AGENTLINT_AGENTCHUTE_POLICY_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_x")

    invalid = MagicMock(status_code=200, content=b"x", headers={})
    invalid.json.return_value = {"rules": [{"id": "", "match": {"operator": "nope"}}]}
    with patch("requests.get", return_value=invalid):
        result = policy.refresh_policy()
    assert result.ok is False
    assert "rules[0].id is required" in (result.error or "")

    huge = MagicMock(status_code=200, content=b"x" * (512 * 1024 + 1), headers={})
    with patch("requests.get", return_value=huge):
        result = policy.refresh_policy()
    assert result.ok is False
    assert result.error == "policy payload too large"


def test_policy_status_records_invalid_cached_policy(tmp_path, monkeypatch):
    from agentlint.agentchute import policy

    monkeypatch.setenv("AGENTLINT_AGENTCHUTE_POLICY_DIR", str(tmp_path))
    (tmp_path / "policy.json").write_text("{not-json", encoding="utf-8")

    assert policy.load_cached_policy() is None
    meta = json.loads((tmp_path / "policy-meta.json").read_text())

    assert "invalid cached policy" in meta["error"]


def test_declarative_policy_rules_match_supported_operators():
    from agentlint.agentchute.policy import build_policy_rules

    raw_rules = [
        {"id": "eq", "match": {"field": "tool_name", "operator": "equals", "value": "Bash"}},
        {"id": "contains", "match": {"field": "command", "operator": "contains", "value": "-rf"}},
        {"id": "starts", "match": {"field": "file_path", "operator": "starts_with", "value": "src/"}},
        {"id": "ends", "match": {"field": "file_path", "operator": "ends_with", "value": ".py"}},
        {"id": "glob", "match": {"field": "file_path", "operator": "glob", "value": "src/*.py"}},
        {"id": "under", "match": {"field": "file_path", "operator": "path_under", "value": "src"}},
        {"id": "verb", "match": {"field": "command", "operator": "command_verb", "value": "rm"}},
        {"id": "pkg", "match": {"field": "tool_input.name", "operator": "package_name", "value": "Requests"}},
        {"id": "disabled", "enabled": False, "match": {"field": "tool_name", "operator": "equals", "value": "Bash"}},
    ]
    rules = build_policy_rules({"rules": raw_rules})
    ctx = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={
            "command": "rm -rf src/app.py",
            "name": "requests",
            "file_path": "src/app.py",
        },
        project_dir="/repo",
    )

    fired = {rule.id for rule in rules for _ in rule.evaluate(ctx)}

    assert fired == {"eq", "contains", "starts", "ends", "glob", "under", "verb", "pkg"}
    assert all(v.severity in {Severity.WARNING, Severity.ERROR, Severity.INFO} for rule in rules for v in rule.evaluate(ctx))


def test_required_packs_filters_and_reports_missing(monkeypatch):
    from importlib.metadata import PackageNotFoundError
    from agentlint.agentchute import policy

    doc = {"required_packs": [{"name": "present"}, {}, "bad", {"name": "missing"}]}
    assert policy.required_packs(doc) == [{"name": "present"}, {"name": "missing"}]

    def fake_version(name: str) -> str:
        if name == "missing":
            raise PackageNotFoundError(name)
        return "1.0.0"

    monkeypatch.setattr(policy, "package_version", fake_version)
    assert policy.missing_required_packs(doc) == ["missing"]


def test_queue_enqueue_flush_dry_run_and_status(tmp_path, monkeypatch):
    from agentlint.agentchute import queue

    monkeypatch.setenv("AGENTLINT_AGENTCHUTE_QUEUE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_x")
    monkeypatch.setenv("AGENTCHUTE_ENABLED", "true")

    event_id = queue.enqueue_event({"tool": "Bash"}, session_key="s1")
    assert event_id
    status = queue.queue_status()
    assert status["queued"] == 1
    assert status["pending"] == 1

    result = queue.flush_queue(dry_run=True)

    assert result.attempted == 1
    assert result.delivered == 1
    assert queue.queue_status()["pending"] == 0


def test_queue_flush_skips_poison_and_records_retry(tmp_path, monkeypatch):
    from agentlint.agentchute import queue

    monkeypatch.setenv("AGENTLINT_AGENTCHUTE_QUEUE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_x")
    monkeypatch.setenv("AGENTCHUTE_ENABLED", "true")
    (tmp_path / "queue.jsonl").write_text(
        "\n{not-json\n" + json.dumps({"event_id": "e1", "event": {}}) + "\n",
        encoding="utf-8",
    )

    with patch("agentlint.agentchute.client.AgentChuteClient.post_events_batch", return_value=None):
        result = queue.flush_queue()

    assert result.skipped == 2
    assert result.attempted == 1
    assert result.failed == 1
    retry = json.loads((tmp_path / "retry.json").read_text())
    assert retry["failures"] == 1
    assert retry["next_attempt_at"] > 0


def test_queue_flush_handles_lock_and_stale_lock(tmp_path, monkeypatch):
    from agentlint.agentchute import queue

    monkeypatch.setenv("AGENTLINT_AGENTCHUTE_QUEUE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_x")
    monkeypatch.setenv("AGENTCHUTE_ENABLED", "true")
    tmp_path.mkdir(exist_ok=True)
    lock = tmp_path / "flush.lock"
    lock.write_text("other", encoding="utf-8")

    assert queue.flush_queue().locked is True

    old = 1
    import os

    os.utime(lock, (old, old))
    assert queue.flush_queue(dry_run=True).locked is False


def test_trigger_background_flush_respects_retry_and_spawns(tmp_path, monkeypatch):
    from agentlint.agentchute import queue

    monkeypatch.setenv("AGENTLINT_AGENTCHUTE_QUEUE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_x")
    monkeypatch.setenv("AGENTCHUTE_ENABLED", "true")
    queue._save_json(tmp_path / "retry.json", {"next_attempt_at": 9999999999})
    with patch("subprocess.Popen") as popen:
        queue.trigger_background_flush()
    popen.assert_not_called()

    queue._clear_retry()
    with patch("subprocess.Popen") as popen:
        queue.trigger_background_flush()
    popen.assert_called_once()


def test_sync_recordings_dry_run_cursor_and_failure(tmp_path, monkeypatch):
    from agentlint.agentchute import sync

    rec_dir = tmp_path / "recordings"
    rec_dir.mkdir()
    rec_file = rec_dir / "abc.jsonl"
    rec_file.write_text(
        "\n{bad\n" + json.dumps({"event": "one"}) + "\n" + json.dumps({"event": "two"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sync, "_recordings_dir", lambda: rec_dir)
    monkeypatch.setattr(
        sync,
        "list_recordings",
        lambda: [{"session_key": "abc", "path": str(rec_file)}],
    )
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_x")

    result = sync.sync_recordings(max_events=1, dry_run=True)

    assert result.files_scanned == 1
    assert result.events_attempted == 1
    assert result.events_succeeded == 1
    assert json.loads((tmp_path / "agentchute-cursor.json").read_text())["abc"] == 3

    with patch("agentlint.agentchute.client.AgentChuteClient.post_event", return_value=False):
        result = sync.sync_recordings(dry_run=False)
    assert result.events_attempted == 1
    assert result.events_failed == 1


def test_sync_aborts_after_three_initial_failures(tmp_path, monkeypatch):
    from agentlint.agentchute import sync

    rec_dir = tmp_path / "recordings"
    rec_dir.mkdir()
    rec_file = rec_dir / "abc.jsonl"
    rec_file.write_text(
        "\n".join(json.dumps({"event": i}) for i in range(3)),
        encoding="utf-8",
    )
    monkeypatch.setattr(sync, "_recordings_dir", lambda: rec_dir)
    monkeypatch.setattr(
        sync,
        "list_recordings",
        lambda: [{"session_key": "abc", "path": str(rec_file)}],
    )
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_x")

    with patch("agentlint.agentchute.client.AgentChuteClient.post_event", return_value=False):
        result = sync.sync_recordings()

    assert result.events_attempted == 3
    assert result.events_failed == 3
    assert result.aborted_reason is not None


def test_sync_reset_cursor(tmp_path, monkeypatch):
    from agentlint.agentchute import sync

    monkeypatch.setattr(sync, "_recordings_dir", lambda: tmp_path / "recordings")
    cursor = tmp_path / "agentchute-cursor.json"
    cursor.write_text('{"s": 1}', encoding="utf-8")

    sync.reset_cursor()

    assert not cursor.exists()
