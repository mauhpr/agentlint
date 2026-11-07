"""Local, passive observations of host tool and approval lifecycle events.

These records never authorize, submit, interrupt or resume a host operation.
SQLite serializes concurrent child hooks independently of session rule state.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from agentlint.evidence import exit_status
from agentlint.recorder import safe_command_summary
from agentlint.session import _cache_dir, workspace_dir

_TERMINAL = {"completed", "tool_failed", "cancelled", "agentlint_blocked", "host_denied"}
_EVENTS = {
    "PreToolUse",
    "PermissionRequest",
    "PostToolUse",
    "PostToolUseFailure",
    "SubagentStart",
    "SubagentStop",
    "Notification",
}


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _label(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value):
        return value
    return "id-" + _digest(value)[:12]


def _path() -> Path:
    return _cache_dir().absolute() / "activity.sqlite3"


def _session_id(raw: dict, platform: str) -> str:
    return (
        raw.get("session_id")
        or os.environ.get(f"{platform.upper()}_SESSION_ID")
        or os.environ.get("AGENTLINT_SESSION_ID")
        or "unknown"
    )


def _identity(raw: dict, platform: str) -> str:
    return platform + ":" + _digest(_session_id(raw, platform))


def _revision(item: dict) -> str:
    return _digest(
        {
            key: item.get(key)
            for key in (
                "state",
                "agent_id",
                "approval_owner",
                "correlation",
                "blocked_rules",
            )
        }
    )


def observe(
    raw: dict,
    *,
    event: str,
    project_dir: str,
    platform: str = "codex",
    blocked_rules: tuple[str, ...] = (),
) -> None:
    """Persist minimized host observations; repeated events never reopen completed calls."""
    if event not in _EVENTS:
        return
    if event == "Notification":
        approval_notice = (
            platform in {"claude", "kimi"} and raw.get("notification_type") == "permission_prompt"
        ) or (platform == "gemini" and raw.get("notification_type") == "ToolPermission")
        if not approval_notice:
            return
        event = "PermissionRequest"
    tool_input = raw.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    workspace = _digest(workspace_dir(project_dir, raw.get("cwd") or project_dir))
    session = _identity(raw, platform)
    actor = _label(raw.get("agent_id"))
    agent_event = event in {"SubagentStart", "SubagentStop"}
    action = _digest(
        {
            "tool": raw.get("tool_name"),
            "input": {key: value for key, value in tool_input.items() if key != "description"},
        }
    )
    invocation = raw.get("tool_use_id")
    turn = raw.get("turn_id") or raw.get("prompt_id")
    key = (
        _digest(["agent", actor])
        if agent_event
        else _digest(
            [
                "action",
                invocation or [turn, actor, action],
            ]
        )
    )
    response = raw.get("tool_response")
    response = response if isinstance(response, dict) else {}
    status = response.get("status")
    code = exit_status(response)
    if agent_event:
        state = "completed" if event == "SubagentStop" else "unknown"
    elif event == "PreToolUse":
        state = "agentlint_blocked" if blocked_rules else "unknown"
    elif event == "PermissionRequest":
        state = "awaiting_approval"
    elif raw.get("failure_type") == "permission_denied" or status == "declined":
        state = "host_denied"
    elif raw.get("is_interrupt") is True or status == "cancelled":
        state = "cancelled"
    elif (
        event == "PostToolUseFailure"
        or code is not None
        and code != 0
        or status == "failed"
        or response.get("error")
        or response.get("isError") is True
    ):
        state = "tool_failed"
    elif status in {"running", "awaiting_approval", "unknown"}:
        state = status
    elif (
        code == 0
        or status == "completed"
        or platform in {"claude", "continue", "kimi", "grok"}
        and event == "PostToolUse"
    ):
        state = "completed"
    else:
        state = "unknown"
    record = {
        "platform": platform,
        "tool_name": _label(raw.get("tool_name")),
        "session_id": _label(_session_id(raw, platform)),
        "tool_use_id": _label(invocation),
        "action_summary": safe_command_summary(
            tool_input["command"] if isinstance(tool_input.get("command"), str) else ""
        ),
        "session_fingerprint": _digest(session)[:12],
        "agent_id": actor,
        "state": state,
        "action_fingerprint": action if raw.get("tool_name") or tool_input else None,
        "approval_owner": _label(raw.get("approval_owner")),
        "correlation": "tool_use_id" if invocation else "action_only",
        "source_event": event,
        "blocked_rules": sorted(set(blocked_rules)),
        "approval_observed": state == "awaiting_approval",
    }
    invocation_hash = _digest(invocation) if invocation else None
    destination = _path()
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(destination, os.O_CREAT | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.close(fd)
    with closing(sqlite3.connect(destination, timeout=1)) as db, db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS observations (workspace TEXT, session TEXT, key TEXT, kind TEXT, action TEXT, actor TEXT, turn TEXT, invocation TEXT, state TEXT, pending INTEGER, updated REAL, payload TEXT, PRIMARY KEY(workspace, session, key))"
        )
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute(
            "SELECT payload, invocation FROM observations WHERE workspace=? AND session=? AND key=?",
            (workspace, session, key),
        ).fetchone()
        if not agent_event and (
            not invocation or (not previous and event in {"PostToolUse", "PostToolUseFailure"})
        ):
            unbound = " AND invocation IS NULL" if invocation else ""
            match = "workspace=? AND session=? AND kind='action' AND action=?"
            match_args = [workspace, session, action]
            if actor is not None:
                match += " AND (actor IS NULL OR actor=?)"
                match_args.append(actor)
            if turn is not None:
                match += " AND (turn IS NULL OR turn=?)"
                match_args.append(turn)
            terminal = ",".join("?" for _ in _TERMINAL)
            candidates = db.execute(
                "SELECT key, payload, invocation FROM observations WHERE "
                + match
                + f" AND state NOT IN ({terminal})"
                + unbound,
                (*match_args, *sorted(_TERMINAL)),
            ).fetchall()
            if len(candidates) == 1:
                matched_key, old_payload, old_invocation = candidates[0]
                previous = (old_payload, old_invocation)
                if invocation and matched_key != key:
                    db.execute(
                        "DELETE FROM observations WHERE workspace=? AND session=? AND key=?",
                        (workspace, session, matched_key),
                    )
                else:
                    key = matched_key
                    invocation_hash = old_invocation
                record["correlation"] = "unique_action_match"
            elif len(candidates) > 1:
                record["correlation"] = "ambiguous"
                record["state"] = state = "unknown"
            elif (
                event == "PermissionRequest"
                and db.execute(
                    "SELECT 1 FROM observations WHERE "
                    + match
                    + f" AND state IN ({terminal}) LIMIT 1",
                    (*match_args, *sorted(_TERMINAL)),
                ).fetchone()
            ):
                record["correlation"] = "unidentified_request"
                record["state"] = state = "unknown"
        old = {}
        if previous:
            old = json.loads(previous[0])
            if not agent_event and old["state"] in _TERMINAL:
                if invocation_hash or event != "PreToolUse":
                    # A late notification is evidence of observation, not a
                    # reason to reopen a terminal action.
                    record = dict(old)
                    state = old["state"]
                # A new ID-less action can reuse the same fingerprint. Its
                # pre-hook proves a new observation, not the old outcome/owner.
                else:
                    old = {}
            if old.get("approval_observed") and state == "unknown":
                record["approval_observed"] = True
            if old.get("approval_owner") and not record["approval_owner"]:
                record["approval_owner"] = old["approval_owner"]
            if old.get("agent_id") and not record["agent_id"] and event != "PermissionRequest":
                record["agent_id"] = old["agent_id"]
            record["observation_id"] = old.get("observation_id") or (
                _digest([workspace, session, key])[:16] if old else None
            )
            record["approval_seen"] = old.get("approval_seen", old.get("approval_observed", False))
            record["first_observed_at"] = old.get("first_observed_at", old.get("observed_at"))
        record["observation_id"] = (
            record.get("observation_id") or _digest([workspace, session, key, time.time_ns()])[:16]
        )
        record["approval_seen"] = record.get("approval_seen", False) or record["approval_observed"]
        record["first_observed_at"] = record.get("first_observed_at") or time.time()
        record["observed_at"] = time.time()
        record["changed_at"] = (
            old.get("changed_at", old.get("observed_at", record["observed_at"]))
            if old and _revision(old) == _revision(record)
            else record["observed_at"]
        )
        db.execute(
            "INSERT OR REPLACE INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                workspace,
                session,
                key,
                "agent" if agent_event else "action",
                action,
                actor,
                turn,
                invocation_hash,
                state,
                int(record["approval_observed"]),
                record["observed_at"],
                json.dumps(record),
            ),
        )


def snapshot(
    project_dir: str,
    *,
    session_id: str | None = None,
    platform: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Read observations without changing files; absence/failure is explicitly unknown."""
    result = {
        "state": "unknown",
        "actions": [],
        "agents": [],
        "error": None,
        "total": 0,
        "truncated": False,
    }
    destination = _path()
    if not destination.exists():
        return result
    query = "SELECT kind, payload, key, session FROM observations WHERE workspace=?"
    args = [_digest(workspace_dir(project_dir))]
    if platform:
        query += " AND session LIKE ?"
        args.append(platform + ":%")
    if session_id:
        if platform:
            query += " AND session=?"
            args.append(_identity({"session_id": session_id}, platform))
        else:
            query += " AND substr(session, instr(session, ':') + 1)=?"
            args.append(_digest(session_id))
    count_query = query.replace("SELECT kind, payload, key, session", "SELECT COUNT(*)")
    query += " ORDER BY pending DESC, updated DESC LIMIT ? OFFSET ?"
    try:
        with closing(sqlite3.connect(destination.as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            result["total"] = db.execute(count_query, args).fetchone()[0]
            result["truncated"] = result["total"] > offset + limit
            rows = db.execute(query, (*args, limit, offset)).fetchall()
        for kind, payload, key, session in rows:
            item = json.loads(payload)
            item.setdefault("observation_id", _digest([args[0], session, key])[:16])
            item["age_seconds"] = max(0, time.time() - item["observed_at"])
            item["stale"] = item["age_seconds"] > 900
            item["live_state_confirmed"] = False
            item["actionable"] = False
            item["correlation_confidence"] = {
                "tool_use_id": "exact",
                "unique_action_match": "inferred",
            }.get(item.get("correlation"), "uncertain")
            item["next_action"] = (
                "Resolve AgentLint rules: " + ", ".join(item.get("blocked_rules", []))
                if item["state"] == "agentlint_blocked"
                else "Verify existing request in host approval UI"
                if item.get("approval_observed")
                else "No approval action observed"
            )
            result["agents" if kind == "agent" else "actions"].append(item)
        result["state"] = "observed" if rows else "unknown"
    except (OSError, sqlite3.Error, ValueError, TypeError):
        result["actions"], result["agents"], result["state"] = [], [], "unknown"
        result["error"] = "Activity observations unavailable; host state unknown"
    return result


def pending_context(
    project_dir: str, session_id: str | None, *, platform: str = "codex"
) -> str | None:
    """Deliver semantic changes once per session, across concurrent hook processes.

    Delivery never changes the observation or the native approval request.
    Timestamps are deliberately excluded: a refresh is not a state change.
    """
    session_id = _session_id({"session_id": session_id}, platform)
    if session_id == "unknown" or not _path().exists():
        return None
    workspace = _digest(workspace_dir(project_dir))
    session = _identity({"session_id": session_id}, platform)
    changed = []
    try:
        with closing(sqlite3.connect(_path(), timeout=1)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS notification_delivery "
                "(workspace TEXT, session TEXT, observation TEXT, revision TEXT, "
                "PRIMARY KEY(workspace, session, observation))"
            )
            rows = db.execute(
                "SELECT key, payload FROM observations WHERE workspace=? AND session=? "
                "AND kind='action' AND (pending=1 OR json_extract(payload, '$.approval_seen')=1) "
                "ORDER BY updated DESC",
                (workspace, session),
            ).fetchall()
            for key, payload in rows:
                item = json.loads(payload)
                if not item.get("approval_seen", item.get("approval_observed")):
                    continue
                identity = item.get("observation_id") or _digest([workspace, session, key])[:16]
                revision = _revision(item)
                previous = db.execute(
                    "SELECT revision FROM notification_delivery "
                    "WHERE workspace=? AND session=? AND observation=?",
                    (workspace, session, identity),
                ).fetchone()
                if previous and previous[0] == revision:
                    continue
                # Historical terminal events need no initial notification.
                if previous or item.get("approval_observed"):
                    changed.append({**item, "observation_id": identity})
                db.execute(
                    "INSERT OR REPLACE INTO notification_delivery VALUES (?, ?, ?, ?)",
                    (workspace, session, identity, revision),
                )
    except (OSError, sqlite3.Error, ValueError, TypeError):
        # A broken observer must not inject an identical failure on every hook.
        # Read-only status exposes the observation error for diagnosis.
        return None
    if not changed:
        return None
    lines = [
        f"Native host approval observations: {len(changed)} change(s) in this session; "
        "last observed, live state unconfirmed."
    ]
    for item in changed[:5]:
        age = max(0, time.time() - item["observed_at"])
        stale = " stale" if age > 900 else ""
        next_action = (
            "verify the existing request in the host UI"
            if item.get("approval_observed")
            else "no approval action remains observed"
        )
        lines.append(
            f"#{item['observation_id']}: host={item['state']}{stale}, "
            f"agent={item.get('agent_id') or 'unknown'}, "
            f"owner={item.get('approval_owner') or 'host approval UI'}, "
            f"correlation={item['correlation']}, observed={age:.0f}s ago. "
            f"Next: {next_action}."
        )
    if any(item.get("approval_observed") for item in changed):
        lines.append(
            "Keep the existing host request; do not interrupt or resubmit it. "
            "AgentLint does not approve or resume host actions."
        )
    else:
        lines.append("AgentLint does not approve or resume host actions.")
    lines.append("Details: agentlint status --history --session-id <session>.")
    return "\n".join(lines)
