"""Degraded AgentChute delivery: throttling, backlog age and health reporting."""

from __future__ import annotations

import json
import sys
import time
import types
from unittest.mock import MagicMock

import pytest

from agentlint.agentchute import queue
from agentlint.agentchute.client import AgentChuteClient, parse_retry_after


@pytest.fixture
def queue_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTLINT_AGENTCHUTE_QUEUE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_x")
    monkeypatch.setenv("AGENTCHUTE_ENABLED", "true")
    return tmp_path


def _fake_requests(monkeypatch, response):
    module = types.ModuleType("requests")
    module.post = MagicMock(return_value=response)
    module.exceptions = types.SimpleNamespace(Timeout=TimeoutError, RequestException=OSError)
    monkeypatch.setitem(sys.modules, "requests", module)
    return module


@pytest.mark.parametrize(
    ("value", "expected"),
    [("120", 120.0), ("0", 0.0), ("99999", 3600.0), ("soon", None), (None, None), ("", None)],
)
def test_parse_retry_after_seconds(value, expected):
    assert parse_retry_after(value) == expected


def test_parse_retry_after_http_date():
    from email.utils import formatdate

    now = time.time()
    assert parse_retry_after(formatdate(now + 60, usegmt=True), now=now) == pytest.approx(60, abs=1)
    assert parse_retry_after(formatdate(now - 60, usegmt=True), now=now) == 0.0


@pytest.mark.parametrize(
    ("status", "outcome"),
    [
        (429, "rate_limited"),
        (503, "server_error"),
        (500, "server_error"),
        (401, "auth_error"),
        (400, "client_error"),
    ],
)
def test_client_classifies_failures(monkeypatch, status, outcome):
    _fake_requests(monkeypatch, MagicMock(status_code=status, headers={"Retry-After": "30"}))
    client = AgentChuteClient(api_url="https://x", license_key="k")
    assert client.post_events_batch([{"event_id": "1"}]) is None
    assert client.last_outcome == outcome
    assert client.last_http_status == status
    assert client.retry_after_s == (30.0 if status in (429, 503) else None)


def test_429_honours_retry_after_and_records_health(queue_dir, monkeypatch):
    _fake_requests(monkeypatch, MagicMock(status_code=429, headers={"Retry-After": "1200"}))
    queue.enqueue_event({"tool": "Bash"}, session_key="s1")
    before = time.time()
    result = queue.flush_queue()
    assert result.failed == 1 and result.aborted_reason == "rate_limited"
    status = queue.queue_status()
    assert status["pending"] == 1
    assert status["next_attempt_at"] >= before + 1200
    assert status["last_outcome"] == "rate_limited"
    assert status["last_http_status"] == 429
    assert status["last_error_at"] >= before
    # The background trigger respects the server-requested window.
    popen = MagicMock()
    monkeypatch.setattr(queue.subprocess, "Popen", popen)
    queue.trigger_background_flush()
    popen.assert_not_called()


def test_success_records_last_success(queue_dir, monkeypatch):
    response = MagicMock(status_code=200)
    response.json.return_value = {"accepted": 1, "duplicates": 0, "failed": []}
    _fake_requests(monkeypatch, response)
    queue.enqueue_event({"tool": "Bash"}, session_key="s1")
    assert queue.flush_queue().delivered == 1
    status = queue.queue_status()
    assert status["pending"] == 0 and status["last_outcome"] == "ok"
    assert status["last_success_at"] is not None


def test_status_reports_backlog_age_size_and_soft_caps(queue_dir, monkeypatch):
    now = time.time()
    lines = [
        json.dumps({"event_id": str(i), "queued_at": now - 3600 + i, "event": {}}) for i in range(3)
    ]
    (queue_dir / "queue.jsonl").write_text("\n".join(lines) + "\n")
    queue._save_json(queue_dir / "cursor.json", {"offset": 1})
    status = queue.queue_status(now=now)
    assert status["pending"] == 2
    assert status["oldest_pending_age_s"] == pytest.approx(3599)
    assert status["bytes"] > 0
    assert status["warnings"] == []
    monkeypatch.setattr(queue, "SOFT_CAP_EVENTS", 2)
    monkeypatch.setattr(queue, "SOFT_CAP_BYTES", 10)
    warnings = queue.queue_status(now=now)["warnings"]
    assert len(warnings) == 2
    # Soft caps never discard anything.
    assert queue.queue_status(now=now)["queued"] == 3


def test_status_on_empty_queue(queue_dir):
    status = queue.queue_status()
    assert status["pending"] == 0
    assert status["oldest_pending_age_s"] is None
    assert status["next_attempt_in_s"] is None
