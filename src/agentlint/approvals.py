"""Typed, expiring, human-issued approvals (docs/approvals-and-evidence.md).

An approval names one action class. It only relaxes rules that declare that
class, only for one repository (and optionally one exact command), and only
until it expires. Approvals never apply to locked, required or organization
rules, and agents cannot create them.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agentlint.utils.shell import simple_words

ACTION_CLASSES = {
    "git-push-protected": "Push (including force-with-lease) to a protected branch",
    "git-merge": "Merge a pull request or branch into a protected branch",
    "infra-apply": "Apply infrastructure changes (terraform/pulumi/kubectl apply)",
    "cloud-delete": "Delete cloud resources",
    "cloud-paid-create": "Create paid cloud resources",
    "destructive-op": "Run a catastrophic or destructive command",
    "cicd-edit": "Edit CI/CD pipeline definitions",
    "package-publish": "Publish a package to a registry",
    "production-access": "Run commands against production targets",
    "model-spend": "Spend model/API budget beyond the configured limit",
}

# Built-in rules that a typed approval may relax, and the class each requires.
RULE_ACTION_CLASS = {
    "no-push-to-main": "git-push-protected",
    "no-force-push": "git-push-protected",
    "dry-run-required": "infra-apply",
    "cloud-infra-mutation": "infra-apply",
    "cloud-resource-deletion": "cloud-delete",
    "cloud-paid-resource-creation": "cloud-paid-create",
    "destructive-confirmation-gate": "destructive-op",
    "no-destructive-commands": "destructive-op",
    "cicd-pipeline-guard": "cicd-edit",
    "package-publish-guard": "package-publish",
    "production-guard": "production-access",
    "token-budget": "model-spend",
    "token-burn-against-team-budget": "model-spend",
}

MAX_TTL = timedelta(hours=24)
DEFAULT_TTL = timedelta(hours=1)
_TTL_RE = re.compile(r"^(\d+)([mhd])$")


def approvals_path() -> Path:
    return Path(
        os.environ.get("AGENTLINT_APPROVALS_FILE", "~/.cache/agentlint/approvals.jsonl")
    ).expanduser()


def _audit_path() -> Path:
    return Path(
        os.environ.get("AGENTLINT_APPROVAL_AUDIT_FILE", "~/.cache/agentlint/approval-audit.jsonl")
    ).expanduser()


def parse_ttl(value: str) -> timedelta:
    match = _TTL_RE.match(value.strip())
    if not match:
        raise ValueError("TTL must look like 30m, 2h or 1d")
    amount, unit = int(match.group(1)), match.group(2)
    ttl = {
        "m": timedelta(minutes=amount),
        "h": timedelta(hours=amount),
        "d": timedelta(days=amount),
    }[unit]
    if ttl <= timedelta(0) or ttl > MAX_TTL:
        raise ValueError("TTL must be greater than zero and at most 24h")
    return ttl


def _literal(command: str) -> list[str] | None:
    if any(char in command for char in ";|&<>()"):
        return None
    return simple_words(command) or None


def _append(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode):
            raise OSError("approvals file is not a regular file")
        if hasattr(os, "fchmod"):
            os.fchmod(file.fileno(), 0o600)
        file.write(json.dumps(record, sort_keys=True) + "\n")
        file.flush()
        os.fsync(file.fileno())


def _records() -> list[dict]:
    try:
        lines = approvals_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


def create_grant(
    action_class: str,
    *,
    repository: str,
    reason: str,
    ttl: timedelta = DEFAULT_TTL,
    operation: str | None = None,
    now: datetime | None = None,
) -> dict:
    if action_class not in ACTION_CLASSES:
        raise ValueError(f"unknown action class '{action_class}'")
    if not reason or not reason.strip():
        raise ValueError("a reason is required")
    if ttl <= timedelta(0) or ttl > MAX_TTL:
        raise ValueError("TTL must be greater than zero and at most 24h")
    if operation is not None and _literal(operation) is None:
        raise ValueError("--operation must be a literal simple command")
    now = now or datetime.now(UTC)
    grant = {
        "type": "grant",
        "id": "apr_" + secrets.token_hex(4),
        "action_class": action_class,
        "repository": str(Path(repository).resolve()),
        "operation": operation,
        "reason": reason.strip(),
        "created_at": now.isoformat(),
        "expires_at": (now + ttl).isoformat(),
    }
    _append(approvals_path(), grant)
    return grant


def revoke_grant(grant_id: str) -> bool:
    if not any(r.get("type") == "grant" and r.get("id") == grant_id for r in _records()):
        return False
    _append(
        approvals_path(),
        {"type": "revoke", "id": grant_id, "at": datetime.now(UTC).isoformat()},
    )
    return True


def active_grants(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(UTC)
    records = _records()
    revoked = {r.get("id") for r in records if r.get("type") == "revoke"}
    grants = []
    for record in records:
        if record.get("type") != "grant" or record.get("id") in revoked:
            continue
        try:
            created = datetime.fromisoformat(record["created_at"])
            expires = datetime.fromisoformat(record["expires_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if expires - created > MAX_TTL or record.get("action_class") not in ACTION_CLASSES:
            continue  # tampered or invalid; never honoured
        if created <= now < expires:
            grants.append(record)
    return grants


def matching_grant(rule_id: str, *, repository: str, command: str | None) -> dict | None:
    """Return an active grant whose class matches this rule, repository and command."""
    action_class = RULE_ACTION_CLASS.get(rule_id)
    if action_class is None:
        return None
    try:
        repo = str(Path(repository).resolve())
    except OSError:
        return None
    for grant in active_grants():
        if grant["action_class"] != action_class or grant.get("repository") != repo:
            continue
        operation = grant.get("operation")
        if operation and (
            not command or _literal(command) is None or _literal(command) != _literal(operation)
        ):
            continue
        return grant
    return None


def audit_use(grant: dict, *, rule_id: str, repository: str, command: str | None) -> bool:
    """Record the use before relaxing the rule; failure keeps the block."""
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "approval_id": grant["id"],
        "action_class": grant["action_class"],
        "rule_id": rule_id,
        "repository": str(Path(repository).resolve()),
        "operation_sha256": hashlib.sha256((command or "").encode()).hexdigest(),
    }
    try:
        _append(_audit_path(), record)
    except OSError:
        return False
    return True


_SELF_GRANT_RE = re.compile(r"\bagentlint\b[^\n;|&]*\bapprove\b[^\n;|&]*\bgrant\b")


def self_approval_attempt(tool_name: str, tool_input: dict) -> str | None:
    """Describe an agent tool call that would create or forge an approval."""
    if tool_name == "Bash":
        command = tool_input.get("command") or ""
        if isinstance(command, str):
            if _SELF_GRANT_RE.search(command):
                return "runs `agentlint approve grant`"
            if approvals_path().name in command and re.search(
                r">|\btee\b|\bcp\b|\bmv\b|\bsed\b", command
            ):
                return "writes the AgentLint approvals file"
        return None
    file_path = tool_input.get("file_path") or ""
    if isinstance(file_path, str) and file_path:
        try:
            if Path(file_path).expanduser().resolve() == approvals_path().resolve():
                return "edits the AgentLint approvals file"
        except OSError:
            return None
    return None
