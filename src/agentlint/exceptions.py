"""Short-lived, exact-command local exceptions with a fail-closed audit trail."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agentlint.utils.shell import simple_words


def _literal_operation(command: str) -> list[str] | None:
    if any(char in command for char in ";|&<>()"):
        return None
    words = simple_words(command)
    if not words or words[0] in {"bash", "sh", "zsh", "python", "python3", "ssh", "sudo"}:
        return None
    return words


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("exception timestamps must include a timezone")
    return parsed.astimezone(UTC)


def validate_exceptions(grants: object) -> list[dict]:
    """Reject broad, malformed or long-lived grants when configuration loads."""
    if grants is None:
        return []
    if not isinstance(grants, list):
        raise ValueError("exceptions must be a list")
    seen: set[str] = set()
    for grant in grants:
        if not isinstance(grant, dict) or not all(
            isinstance(grant.get(key), str) and grant[key].strip()
            for key in (
                "id",
                "rule_id",
                "repository",
                "operation",
                "created_at",
                "expires_at",
                "reason",
            )
        ):
            raise ValueError(
                "each exception requires id, rule_id, repository, operation, created_at, expires_at and reason"
            )
        if grant["id"] in seen or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", grant["id"]):
            raise ValueError("exception IDs must be unique and use letters, digits, _ or -")
        seen.add(grant["id"])
        if not Path(grant["repository"]).is_absolute():
            raise ValueError("exception repository must be an absolute path")
        if not _literal_operation(grant["operation"]):
            raise ValueError("exception operation must be a literal simple command")
        try:
            created = _timestamp(grant["created_at"])
            expires = _timestamp(grant["expires_at"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid exception timestamp: {exc}") from exc
        if expires <= created or expires - created > timedelta(days=7):
            raise ValueError("exception lifetime must be at most seven days")
    return grants


def applies(grant: dict, *, rule_id: str, repository: str, command: str) -> bool:
    now = datetime.now(UTC)
    try:
        return (
            grant["rule_id"] == rule_id
            and Path(grant["repository"]).resolve() == Path(repository).resolve()
            and _literal_operation(grant["operation"]) == _literal_operation(command)
            and _literal_operation(command) is not None
            and _timestamp(grant["created_at"]) <= now < _timestamp(grant["expires_at"])
        )
    except (KeyError, OSError, ValueError, TypeError):
        return False


def audit_use(grant: dict, *, repository: str, command: str) -> bool:
    """Write an audit record before granting the exception; failure keeps the block."""
    path = Path(
        os.environ.get("AGENTLINT_EXCEPTION_AUDIT_FILE", "~/.cache/agentlint/exception-audit.jsonl")
    ).expanduser()
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "exception_id": grant["id"],
        "rule_id": grant["rule_id"],
        "repository": str(Path(repository).resolve()),
        "operation_sha256": hashlib.sha256(command.encode()).hexdigest(),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as file:
            if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
                return False
            if hasattr(os, "fchmod"):
                os.fchmod(file.fileno(), 0o600)
            file.write(json.dumps(record, sort_keys=True) + "\n")
            file.flush()
            os.fsync(file.fileno())
    except OSError:
        return False
    return True
