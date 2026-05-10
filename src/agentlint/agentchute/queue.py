"""Durable local event queue for AgentChute.

The hook path appends one privacy-safe JSON line and returns. Network
delivery is handled later by a short-lived background flusher process.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentlint.agentchute.client import AgentChuteClient, is_agentchute_enabled

logger = logging.getLogger("agentlint.agentchute.queue")

_DEFAULT_BATCH_SIZE = 50
_DEFAULT_TIME_BUDGET_S = 3.0
_MAX_EVENT_BYTES = 65_536
_BACKOFF_CAP_S = 300


def _queue_root() -> Path:
    return Path(
        os.environ.get("AGENTLINT_AGENTCHUTE_QUEUE_DIR", "~/.cache/agentlint/agentchute/events")
    ).expanduser()


def _queue_path() -> Path:
    return _queue_root() / "queue.jsonl"


def _cursor_path() -> Path:
    return _queue_root() / "cursor.json"


def _lock_path() -> Path:
    return _queue_root() / "flush.lock"


def _retry_path() -> Path:
    return _queue_root() / "retry.json"


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def enqueue_event(event: dict, *, session_key: str, config: Any | None = None) -> str | None:
    """Append one event to the durable AgentChute queue.

    Returns the generated event_id, or None if AgentChute is not enabled.
    """
    if not is_agentchute_enabled(config):
        return None

    root = _queue_root()
    root.mkdir(parents=True, exist_ok=True)
    line_offset = _count_lines(_queue_path())
    event_id = uuid.uuid4().hex
    queued = {
        "v": 1,
        "event_id": event_id,
        "session_key": session_key,
        "line_offset": line_offset,
        "queued_at": time.time(),
        "event": event,
    }
    raw = json.dumps(queued, separators=(",", ":"))
    if len(raw.encode("utf-8")) > _MAX_EVENT_BYTES:
        logger.warning("agentlint.agentchute: event too large; not queued")
        return None
    with open(_queue_path(), "a", encoding="utf-8") as f:
        f.write(raw + "\n")
    return event_id


def trigger_background_flush(config: Any | None = None) -> None:
    """Start a detached flusher process if AgentChute is enabled.

    Failures are intentionally swallowed; delivery will retry on a later
    hook, status command, or explicit flush.
    """
    if not is_agentchute_enabled(config):
        return
    retry = _load_json(_retry_path(), {})
    next_attempt_at = float(retry.get("next_attempt_at", 0) or 0)
    if next_attempt_at and time.time() < next_attempt_at:
        return
    try:
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "agentlint.cli",
                "agentchute",
                "flush",
                "--background",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:  # noqa: BLE001
        logger.debug("agentlint.agentchute: failed to spawn flusher", exc_info=True)


@dataclass
class FlushResult:
    attempted: int = 0
    delivered: int = 0
    failed: int = 0
    skipped: int = 0
    locked: bool = False
    aborted_reason: str | None = None


def flush_queue(
    *,
    max_events: int | None = None,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    time_budget_s: float = _DEFAULT_TIME_BUDGET_S,
    dry_run: bool = False,
) -> FlushResult:
    """Flush queued events to AgentChute in bounded batches."""
    result = FlushResult()
    client = AgentChuteClient.from_env()
    if client is None:
        result.aborted_reason = "AGENTCHUTE_LICENSE_KEY not set"
        return result

    if not _acquire_lock():
        result.locked = True
        return result

    try:
        deadline = time.time() + time_budget_s
        cursor = int(_load_json(_cursor_path(), {"offset": 0}).get("offset", 0))
        lines = _read_lines()
        if cursor >= len(lines):
            _clear_retry()
            return result

        pending = lines[cursor:]
        if max_events is not None:
            pending = pending[:max_events]

        index = 0
        while index < len(pending) and time.time() < deadline:
            raw_batch = pending[index:index + batch_size]
            batch: list[dict] = []
            poison = 0
            for raw in raw_batch:
                if not raw.strip():
                    poison += 1
                    continue
                try:
                    batch.append(json.loads(raw))
                except json.JSONDecodeError:
                    poison += 1
            if poison:
                cursor += poison
                result.skipped += poison

            if not batch:
                index += len(raw_batch)
                _save_json(_cursor_path(), {"offset": cursor})
                continue

            result.attempted += len(batch)
            if dry_run:
                result.delivered += len(batch)
                cursor += len(raw_batch)
                index += len(raw_batch)
                _save_json(_cursor_path(), {"offset": cursor})
                continue

            response = client.post_events_batch(batch)
            if response is None:
                result.failed += len(batch)
                _record_failure()
                return result

            failed_ids = set(response.get("failed") or [])
            if failed_ids:
                result.failed += len(failed_ids)
                _record_failure()
                return result

            delivered = int(response.get("accepted", 0) or 0) + int(response.get("duplicates", 0) or 0)
            if delivered <= 0:
                delivered = len(batch)
            result.delivered += min(delivered, len(batch))
            cursor += len(raw_batch)
            index += len(raw_batch)
            _save_json(_cursor_path(), {"offset": cursor})
            _clear_retry()

        return result
    finally:
        _release_lock()


def queue_status() -> dict:
    lines = _read_lines()
    cursor = int(_load_json(_cursor_path(), {"offset": 0}).get("offset", 0))
    retry = _load_json(_retry_path(), {})
    pending = max(0, len(lines) - cursor)
    return {
        "queue_path": str(_queue_path()),
        "queued": len(lines),
        "delivered_cursor": cursor,
        "pending": pending,
        "next_attempt_at": retry.get("next_attempt_at"),
        "failures": retry.get("failures", 0),
    }


def _read_lines() -> list[str]:
    path = _queue_path()
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def _acquire_lock() -> bool:
    root = _queue_root()
    root.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(_lock_path(), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except FileExistsError:
        try:
            age = time.time() - _lock_path().stat().st_mtime
        except OSError:
            return False
        if age > 30:
            try:
                _lock_path().unlink()
            except OSError:
                return False
            return _acquire_lock()
        return False


def _release_lock() -> None:
    try:
        _lock_path().unlink()
    except OSError:
        pass


def _record_failure() -> None:
    retry = _load_json(_retry_path(), {})
    failures = int(retry.get("failures", 0) or 0) + 1
    delay = min(_BACKOFF_CAP_S, 2 ** min(failures, 8))
    _save_json(_retry_path(), {"failures": failures, "next_attempt_at": time.time() + delay})


def _clear_retry() -> None:
    try:
        _retry_path().unlink()
    except OSError:
        pass
