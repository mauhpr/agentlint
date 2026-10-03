"""Credential-free hook diagnostics and Codex response validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agentlint.recorder import safe_command_summary


def validate_codex_output(output: str | None, *, event: str, exit_code: int, blocked: bool) -> dict:
    """Check the two documented Codex feedback paths before emitting output."""
    if not output:
        return {"valid": not blocked, "reason": "no output" if blocked else "no violations"}
    try:
        payload = json.loads(output)
    except (TypeError, json.JSONDecodeError):
        return {"valid": False, "reason": "output is not JSON"}
    if not isinstance(payload, dict):
        return {"valid": False, "reason": "output is not an object"}
    if exit_code != 0:
        return {"valid": False, "reason": "structured JSON requires exit 0"}
    specific = payload.get("hookSpecificOutput")
    if specific is not None and (
        not isinstance(specific, dict) or specific.get("hookEventName") != event
    ):
        return {"valid": False, "reason": "hookEventName does not match event"}
    if blocked and event == "PreToolUse":
        if not isinstance(specific, dict) or specific.get("permissionDecision") != "deny":
            return {"valid": False, "reason": "missing PreToolUse deny decision"}
    elif (
        blocked
        and event in {"PostToolUse", "PostToolUseFailure", "UserPromptSubmit"}
        and (payload.get("decision") != "block" or not payload.get("reason"))
    ):
        return {"valid": False, "reason": "missing block decision or reason"}
    return {"valid": True, "reason": "Codex JSON protocol"}


def write_bundle(
    path: str,
    *,
    raw: dict,
    event: str,
    adapter: str,
    version: str,
    project_dir: str,
    rules_evaluated: int,
    rule_ids_evaluated: list[str],
    violations: list,
    validation: dict,
) -> None:
    """Write minimized input shape and decisions, excluding raw arguments and messages."""
    tool_input = raw.get("tool_input") or {}
    tool = raw.get("tool_name", "")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    bundle = {
        "schema_version": 1,
        "adapter": adapter,
        "agentlint_version": version,
        "event": event,
        "project_sha256": hashlib.sha256(project_dir.encode()).hexdigest(),
        "tool_name": tool
        if tool in {"Bash", "apply_patch", "Read", "Write", "Edit"}
        else "[other tool]",
        "tool_input_keys": (
            sorted(
                set(tool_input)
                & {
                    "command",
                    "file_path",
                    "workdir",
                    "cwd",
                    "patch",
                    "content",
                    "old_string",
                    "new_string",
                }
            )
            if isinstance(tool_input, dict)
            else []
        ),
        "other_input_keys": (
            len(
                set(tool_input)
                - {
                    "command",
                    "file_path",
                    "workdir",
                    "cwd",
                    "patch",
                    "content",
                    "old_string",
                    "new_string",
                }
            )
            if isinstance(tool_input, dict)
            else 0
        ),
        "command_summary": safe_command_summary(command) if tool == "Bash" else None,
        "input_sha256": (
            hashlib.sha256(command.encode()).hexdigest() if isinstance(command, str) else None
        ),
        "rules_evaluated": rules_evaluated,
        "rule_ids_evaluated": rule_ids_evaluated,
        "violations": [
            {"rule_id": item.rule_id, "severity": item.severity.value} for item in violations
        ],
        "output_validation": validation,
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    destination.chmod(0o600)
