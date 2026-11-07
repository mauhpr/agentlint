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
from urllib.parse import parse_qs, urlsplit

from agentlint.utils.shell import simple_words, unwrap_simple_command

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
    "fixture-copy": "Copy one hash-bound local file into a repository fixture directory",
    "cloud-upload": "Upload one hash-bound file to one create-only cloud object",
    "secret-finding": "Acknowledge one reviewed secret finding in one source file",
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
    "no-bash-file-write": "fixture-copy",
    "no-network-exfil": "cloud-upload",
    "no-secrets": "secret-finding",
}

MAX_TTL = timedelta(hours=24)
DEFAULT_TTL = timedelta(hours=1)
MAX_FIXTURE_BYTES = 5_000_000
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
    return simple_words(command) or None


def _fixture_copy_scope(repository: str, operation: str | None) -> dict:
    """Bound one literal cp to regular files inside this worktree and a source hash."""
    words = _literal(operation) if operation else None
    if not words or len(words) != 3 or words[0] not in {"cp", "/bin/cp", "/usr/bin/cp"}:
        raise ValueError(
            "fixture-copy requires --operation 'cp /absolute/source /absolute/fixtures/target'"
        )
    root = Path(repository).resolve()
    paths = [Path(word) for word in words[1:]]
    if not all(path.is_absolute() and not path.is_symlink() for path in paths):
        raise ValueError("fixture-copy paths must be absolute and must not be symlinks")
    source, destination = (path.resolve() for path in paths)
    if not all(path.is_relative_to(root) and path != root for path in (source, destination)):
        raise ValueError(
            "fixture-copy source and destination must stay inside the approved worktree"
        )
    if not {"fixtures", "testdata"}.intersection(destination.relative_to(root).parts[:-1]):
        raise ValueError("fixture-copy destination must be in a fixtures/ or testdata/ directory")
    if not source.is_file() or not destination.parent.is_dir() or destination.is_dir():
        raise ValueError(
            "fixture-copy requires a regular source and an existing destination directory"
        )
    with source.open("rb") as file:
        data = file.read(MAX_FIXTURE_BYTES + 1)
    if len(data) > MAX_FIXTURE_BYTES:
        raise ValueError("fixture-copy source exceeds the 5 MB limit")
    digest = hashlib.sha256(data).hexdigest()
    if destination.exists():
        if not destination.is_file() or destination.stat().st_size > MAX_FIXTURE_BYTES:
            raise ValueError("fixture-copy cannot overwrite a different destination")
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise ValueError("fixture-copy cannot overwrite a different destination")
    return {"source": str(source), "destination": str(destination), "source_sha256": digest}


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


def _upload_scope(operation: str | None, max_bytes: int | None) -> dict:
    """Inspect an exact create-only GCS upload with bounded-memory hashing."""
    words = _literal(operation) if operation else None
    words = unwrap_simple_command(words) if words else None
    if (
        not words
        or Path(words[0]).name != "curl"
        or len(words) not in {7, 9}
        or words[1:5] != ["--disable", "--request", "POST", "--upload-file"]
    ):
        raise ValueError(
            "cloud-upload requires curl --disable --request POST --upload-file /source [--header @/headers] EXACT_GCS_JSON_UPLOAD_URL; gcloud cp has folder inference"
        )
    source_name = words[5]
    if any(char in source_name for char in "*?[]{}") or any(char in words[-1] for char in "[]{}*"):
        raise ValueError("cloud-upload requires literal paths without shell or URL globs")
    if len(words) == 9:
        if words[6] != "--header" or not words[7].startswith("@/"):
            raise ValueError("cloud-upload authentication must use --header @/absolute/header-file")
        headers = Path(words[7][1:])
        if headers.is_symlink():
            raise ValueError("cloud-upload header file must be a small regular file")
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        with os.fdopen(os.open(headers, flags), "rb") as file:
            metadata = os.fstat(file.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 16384:
                raise ValueError("cloud-upload header file must be a small regular file")
            data = file.read(16385)
        if len(data) > 16384:
            raise ValueError("cloud-upload header file exceeds its size limit")
        lines = data.decode().splitlines()
        if not lines or not all(
            re.fullmatch(
                r"(?:Authorization: Bearer [A-Za-z0-9._~+/-]+=*|Content-Type: [A-Za-z0-9.+/-]+)",
                line,
            )
            for line in lines
        ):
            raise ValueError(
                "cloud-upload header file may only supply Authorization and Content-Type"
            )
    url = urlsplit(words[-1])
    path = re.fullmatch(r"/upload/storage/v1/b/([A-Za-z0-9][A-Za-z0-9._-]*)/o", url.path)
    query = parse_qs(url.query, keep_blank_values=True)
    if (
        url.scheme != "https"
        or url.netloc != "storage.googleapis.com"
        or url.fragment
        or not path
        or set(query) != {"uploadType", "name", "ifGenerationMatch"}
        or query["uploadType"] != ["media"]
        or query["ifGenerationMatch"] != ["0"]
        or len(query["name"]) != 1
        or not query["name"][0]
    ):
        raise ValueError(
            "cloud-upload requires an exact JSON media upload URL with name and ifGenerationMatch=0"
        )
    destination = f"gs://{path[1]}/{query['name'][0]}"
    source = Path(source_name)
    if not source.is_absolute() or source.is_symlink() or not source.is_file():
        raise ValueError("cloud-upload source must be an absolute regular file, not a symlink")
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
        raise ValueError("cloud-upload requires a positive --max-bytes size limit")
    digest = hashlib.sha256()
    size = 0
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(source, flags), "rb") as file:
        before = os.fstat(file.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > max_bytes:
            raise ValueError("cloud-upload source exceeds its size limit or is not a regular file")
        while data := file.read(1024 * 1024):
            size += len(data)
            if size > max_bytes:
                raise ValueError("cloud-upload source exceeds its size limit")
            digest.update(data)
        after = os.fstat(file.fileno())
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise ValueError("cloud-upload source changed during inspection")
    return {
        "source": str(source.resolve()),
        "destination": destination,
        "source_sha256": digest.hexdigest(),
        "size_bytes": size,
        "max_bytes": max_bytes,
        "create_only": True,
    }


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
    max_bytes: int | None = None,
    file_path: str | None = None,
    finding_id: str | None = None,
    rule_id: str | None = None,
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
    copy_scope = (
        _fixture_copy_scope(repository, operation) if action_class == "fixture-copy" else None
    )
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
    if copy_scope:
        grant["fixture_copy"] = copy_scope
    if action_class == "cloud-upload":
        grant["upload"] = _upload_scope(operation, max_bytes)
    if action_class == "secret-finding":
        if rule_id != "no-secrets":
            raise ValueError("secret-finding requires the exact --rule-id")
        if not finding_id or not re.fullmatch(r"[a-f0-9]{64}", finding_id):
            raise ValueError("secret-finding requires a 64-character --finding-id")
        if not file_path or not Path(file_path).is_absolute():
            raise ValueError("secret-finding requires an absolute --file-path")
        path = Path(file_path).resolve()
        if not path.is_relative_to(Path(repository).resolve()) or not path.is_file():
            raise ValueError("secret-finding file must exist inside the approved repository")
        grant["finding"] = {"file_path": str(path), "finding_id": finding_id, "rule_id": rule_id}
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


def matching_grant(
    rule_id: str,
    *,
    repository: str,
    command: str | None,
    file_path: str | None = None,
    finding_id: str | None = None,
) -> dict | None:
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
        if action_class == "fixture-copy":
            try:
                if _fixture_copy_scope(repository, command) != grant.get("fixture_copy"):
                    continue
            except (ValueError, OSError):
                continue
        if action_class == "cloud-upload":
            upload = grant.get("upload")
            if not isinstance(upload, dict):
                continue
            try:
                if _upload_scope(command, upload.get("max_bytes")) != upload:
                    continue
            except (ValueError, OSError):
                continue
        if action_class == "secret-finding":
            if not file_path or not finding_id:
                continue
            if grant.get("finding") != {
                "file_path": str(Path(file_path).resolve()),
                "finding_id": finding_id,
                "rule_id": rule_id,
            }:
                continue
        # Hashing a large upload can outlast the grant's remaining lifetime.
        if datetime.now(UTC) >= datetime.fromisoformat(grant["expires_at"]):
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
    if grant.get("action_class") == "fixture-copy":
        record["fixture_copy"] = grant["fixture_copy"]
    if grant.get("action_class") == "cloud-upload":
        record["upload"] = grant["upload"]
    if grant.get("action_class") == "secret-finding":
        record["finding"] = grant["finding"]
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
                # Only exempt a parsed, literal help invocation. A later grant
                # or opaque shell body must never hide behind an earlier --help.
                words = simple_words(command)
                if words == ["agentlint", "approve", "grant", "--help"]:
                    return None
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
