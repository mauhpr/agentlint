"""Session recording for product insights.

Opt-in, privacy-respecting recording that captures lightweight event
summaries (never full file contents) to a JSONL file per session.

Enable via ``recording.enabled: true`` in agentlint.yml or the
``AGENTLINT_RECORDING=1`` environment variable.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Path helpers (lazy — avoids module-level expanduser)
# ---------------------------------------------------------------------------

def _recordings_dir() -> Path:
    """Return the recordings directory, reading env var lazily."""
    return Path(
        os.environ.get("AGENTLINT_RECORDINGS_DIR", "~/.cache/agentlint/recordings")
    ).expanduser()


def _recording_path(key: str) -> Path:
    import re
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", key)
    return _recordings_dir() / f"{safe}.jsonl"


# ---------------------------------------------------------------------------
# Opt-in gate
# ---------------------------------------------------------------------------

def is_recording_enabled(config) -> bool:
    """Check config + env var to decide whether recording is active."""
    if os.environ.get("AGENTLINT_RECORDING") == "1":
        return True
    return config.is_recording_enabled


# ---------------------------------------------------------------------------
# Data minimization
# ---------------------------------------------------------------------------

_BASH_COMMAND_LIMIT = 200
_PROMPT_LIMIT = 100


def summarize_tool_input(
    tool_name: str,
    tool_input: dict,
    prompt: str | None = None,
) -> dict:
    """Return a privacy-safe summary of the tool invocation."""
    summary: dict = {
        "command": None,
        "file_path": None,
        "content_length": None,
    }

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        summary["command"] = cmd[:_BASH_COMMAND_LIMIT]
    elif tool_name in ("Write", "Edit", "MultiEdit"):
        summary["file_path"] = tool_input.get("file_path")
        content = tool_input.get("content") or tool_input.get("new_string") or ""
        summary["content_length"] = len(content) if content else 0
        old_content = tool_input.get("old_string") or ""
        if old_content:
            summary["old_content_length"] = len(old_content)
    elif tool_name in ("Read", "Glob", "Grep"):
        summary["file_path"] = tool_input.get("file_path") or tool_input.get("pattern")
    elif tool_name in ("Agent", "Task"):
        summary["subagent_type"] = tool_input.get("subagent_type")
        desc = tool_input.get("description", "")
        summary["description"] = desc[:_PROMPT_LIMIT] if desc else None
    elif tool_name == "WebFetch":
        summary["url"] = tool_input.get("url", "")[:_BASH_COMMAND_LIMIT]
    elif tool_name == "WebSearch":
        summary["query"] = tool_input.get("query", "")[:_BASH_COMMAND_LIMIT]
    elif tool_name == "NotebookEdit":
        summary["file_path"] = tool_input.get("file_path")
        summary["cell_index"] = tool_input.get("cell_number")
    elif tool_name == "UserPromptSubmit":
        if prompt:
            summary["prompt_preview"] = prompt[:_PROMPT_LIMIT]

    return summary


# ---------------------------------------------------------------------------
# Append / Load
# ---------------------------------------------------------------------------

def append_event(entry: dict, key: str) -> None:
    """Append one JSONL line to the recording file for *key*."""
    path = _recording_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, separators=(",", ":")) + "\n")


def load_recording(key: str) -> list[dict]:
    """Read all event lines from a recording."""
    path = _recording_path(key)
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


# ---------------------------------------------------------------------------
# Listing & stats
# ---------------------------------------------------------------------------

def list_recordings() -> list[dict]:
    """Return metadata for every recording file found."""
    rdir = _recordings_dir()
    if not rdir.exists():
        return []
    results = []
    for p in sorted(rdir.glob("*.jsonl")):
        stat = p.stat()
        # Count lines without loading full JSON
        line_count = sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip())
        results.append({
            "session_key": p.stem,
            "path": str(p),
            "event_count": line_count,
            "size_bytes": stat.st_size,
            "modified": stat.st_mtime,
        })
    return results


def recording_stats(keys: list[str] | None = None) -> dict:
    """Aggregate stats across recordings.

    Returns top tools, top rules fired, and event type distribution.
    """
    tool_counts: dict[str, int] = {}
    rule_counts: dict[str, int] = {}
    event_counts: dict[str, int] = {}
    total_events = 0

    recordings = list_recordings()
    if keys:
        recordings = [r for r in recordings if r["session_key"] in keys]

    for rec in recordings:
        events = load_recording(rec["session_key"])
        for ev in events:
            total_events += 1
            # Tool distribution
            tn = ev.get("tool_name", "")
            if tn:
                tool_counts[tn] = tool_counts.get(tn, 0) + 1
            # Event type distribution
            et = ev.get("event", "")
            if et:
                event_counts[et] = event_counts.get(et, 0) + 1
            # Rule violations
            for v in ev.get("violations", []):
                rid = v.get("rule_id", "")
                if rid:
                    rule_counts[rid] = rule_counts.get(rid, 0) + 1

    return {
        "total_events": total_events,
        "sessions": len(recordings),
        "top_tools": sorted(tool_counts.items(), key=lambda x: x[1], reverse=True),
        "top_rules": sorted(rule_counts.items(), key=lambda x: x[1], reverse=True),
        "event_types": sorted(event_counts.items(), key=lambda x: x[1], reverse=True),
    }


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def clear_recordings(older_than_days: int | None = None) -> int:
    """Delete recording files. Returns count of files removed."""
    rdir = _recordings_dir()
    if not rdir.exists():
        return 0
    now = time.time()
    removed = 0
    for p in rdir.glob("*.jsonl"):
        if older_than_days is not None:
            age_days = (now - p.stat().st_mtime) / 86400
            if age_days < older_than_days:
                continue
        p.unlink()
        removed += 1
    return removed
