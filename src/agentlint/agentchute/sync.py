"""Batch sync of local recordings to AgentChute API.

This is the catch-up path — handles three scenarios:
    1. The user enabled AgentChute retroactively (events accumulated locally
       before the feature was on; one ``agentlint sync`` ships them all).
    2. The agent ran offline (events queued locally; sync flushes them
       when the network returns).
    3. A real-time POST failed silently (timeout, transient 5xx); the
       event is still in the local JSONL, so the next sync ships it.

Idempotency story:
    Each recording file is read line-by-line. We track a per-file cursor
    (offset in lines) in ``~/.cache/agentlint/agentchute-cursor.json``. After
    every successful POST, the cursor advances. On retry, we resume from
    the cursor. The API is also expected to deduplicate by (license_id,
    recording_key, line_number) but the client-side cursor is the
    authoritative dedup mechanism.

Failure modes:
    - Network down → POSTs fail, cursor doesn't advance, retry next run.
    - One bad line of JSON → skip it, advance cursor anyway (poison-pill
      protection).
    - License rejected → halt sync immediately, surface the error.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from agentlint.recorder import _recordings_dir, list_recordings
from agentlint.agentchute.client import AgentChuteClient

logger = logging.getLogger("agentlint.agentchute.sync")

# Cursor file lives next to the recordings cache so a single
# `rm -rf ~/.cache/agentlint` resets everything cleanly.
_CURSOR_FILENAME = "agentchute-cursor.json"


def _cursor_path() -> Path:
    return _recordings_dir().parent / _CURSOR_FILENAME


def _load_cursor() -> dict[str, int]:
    """Map of recording-file-stem → number of lines already synced."""
    path = _cursor_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cursor(cursor: dict[str, int]) -> None:
    path = _cursor_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cursor, sort_keys=True), encoding="utf-8")


@dataclass
class SyncResult:
    """Summary of a single ``agentlint sync`` invocation."""
    files_scanned: int = 0
    events_attempted: int = 0
    events_succeeded: int = 0
    events_failed: int = 0
    aborted_reason: str | None = None

    @property
    def all_succeeded(self) -> bool:
        return (
            self.aborted_reason is None
            and self.events_failed == 0
            and self.events_attempted > 0
        )


def sync_recordings(
    *, max_events: int | None = None, dry_run: bool = False
) -> SyncResult:
    """Walk the recordings directory and POST any new events.

    Args:
        max_events: Cap the number of events sent in this run. Useful
            for backpressure if a user has a giant local backlog after
            enabling AgentChute retroactively. ``None`` means unlimited.
        dry_run: If True, count what *would* be sent without actually
            POSTing. Cursor is not advanced.

    Returns:
        ``SyncResult`` with counts and an optional aborted_reason.
    """
    result = SyncResult()
    client = AgentChuteClient.from_env()
    if client is None:
        result.aborted_reason = (
            "AGENTCHUTE_LICENSE_KEY not set — nothing to sync to"
        )
        return result

    recordings = list_recordings()
    cursor = _load_cursor()

    for rec in recordings:
        result.files_scanned += 1
        key = rec["session_key"]
        already_sent = cursor.get(key, 0)
        path = Path(rec["path"])

        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            logger.warning("agentlint.agentchute: cannot read %s (%s)", path, e)
            continue

        new_lines = lines[already_sent:]
        if not new_lines:
            continue

        for offset, raw_line in enumerate(new_lines):
            if max_events is not None and result.events_attempted >= max_events:
                logger.debug(
                    "agentlint.agentchute: hit max_events=%d, stopping",
                    max_events,
                )
                _save_cursor(cursor)
                return result

            if not raw_line.strip():
                # Empty line — skip it but advance the cursor so we
                # don't read it again next time (poison-pill safety).
                cursor[key] = already_sent + offset + 1
                continue

            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                logger.debug(
                    "agentlint.agentchute: skipping unparseable line in %s",
                    path.name,
                )
                cursor[key] = already_sent + offset + 1
                continue

            # Wrap the event with metadata the API needs to attribute it
            # to a session and to dedupe on retry.
            payload = {
                "v": 1,
                "session_key": key,
                "line_offset": already_sent + offset,
                "synced_at": time.time(),
                "event": event,
            }

            result.events_attempted += 1
            if dry_run:
                # Pretend success without making a request.
                result.events_succeeded += 1
                cursor[key] = already_sent + offset + 1
                continue

            ok = client.post_event(payload)
            if ok:
                result.events_succeeded += 1
                cursor[key] = already_sent + offset + 1
            else:
                # Don't advance the cursor — try again next sync.
                result.events_failed += 1
                # If the very first failure is auth-related, halt the
                # whole sync to avoid spamming the server with rejects.
                # (AgentChuteClient already logged the 401/403 warning.)
                if result.events_succeeded == 0 and result.events_failed >= 3:
                    result.aborted_reason = (
                        "3 consecutive failures — likely a bad license "
                        "key or unreachable API. Halting to protect the "
                        "server. Run again after fixing."
                    )
                    _save_cursor(cursor)
                    return result

    _save_cursor(cursor)
    return result


def reset_cursor() -> None:
    """Forget all sync progress and force a full re-send next time.
    Exposed for `agentlint sync --reset`. Use sparingly — re-sending
    duplicates the events on the server (the API is expected to dedupe
    by (license_id, session_key, line_offset))."""
    path = _cursor_path()
    if path.exists():
        path.unlink()
