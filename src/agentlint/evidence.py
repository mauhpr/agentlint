"""Evidence receipts (docs/approvals-and-evidence.md): what has actually been verified, by whom, when.

Receipts are small JSON files. AgentLint writes `test-run` receipts for
recognized test commands; other tools may write `test-run`, `review` or
`deploy-verified` receipts into configured directories. Receipts are advisory
evidence only and never unblock an ERROR.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from agentlint.utils.shell import split_operations, unwrap_simple_command

KINDS = ("test-run", "review", "deploy-verified")
LEVEL_LABELS = {
    "test-run": "local tests",
    "review": "reviewed code",
    "deploy-verified": "verified deployment",
}
DEFAULT_MAX_AGE_S = 24 * 3600
_LEGACY_TEST_RUNNERS = ("pytest", "vitest", "jest", "npm test", "make test")
_RUN_WRAPPERS = {
    ("uv", "run"),
    ("poetry", "run"),
    ("pipenv", "run"),
    ("pdm", "run"),
    ("rye", "run"),
    ("hatch", "run"),
    ("npx",),
    ("pnpm", "exec"),
    ("yarn", "exec"),
    ("bunx",),
}
# uv/poetry options that consume a value, so the runner after them is found.
_VALUE_OPTIONS = {
    "--with",
    "--extra",
    "--group",
    "--python",
    "-p",
    "--directory",
    "--project",
    "--env-file",
}


def receipts_dir() -> Path:
    return Path(
        os.environ.get("AGENTLINT_RECEIPTS_DIR", "~/.cache/agentlint/receipts")
    ).expanduser()


def _strip_wrappers(words: list[str]) -> list[str]:
    words = unwrap_simple_command(words) or words
    for wrapper in _RUN_WRAPPERS:
        if tuple(words[: len(wrapper)]) == wrapper:
            rest = words[len(wrapper) :]
            while rest and rest[0].startswith("-"):
                option = rest.pop(0)
                if option in _VALUE_OPTIONS and rest and "=" not in option:
                    rest.pop(0)
            return rest
    return words


def _is_test_words(words: list[str]) -> bool:
    words = _strip_wrappers(list(words))
    if not words:
        return False
    binary = words[0].rsplit("/", 1)[-1]
    args = words[1:]
    if binary in {"pytest", "py.test", "vitest", "jest", "tox", "nox"}:
        return True
    if re.fullmatch(r"python(3(\.\d+)?)?", binary) and args[:2] == ["-m", "pytest"]:
        return True
    if binary == "make" and any(re.fullmatch(r"test[\w-]*|check", a) for a in args):
        return True
    runs_test_script = args[:1] == ["test"] or (
        args[:1] == ["run"] and len(args) > 1 and args[1].startswith("test")
    )
    if binary in {"npm", "pnpm", "yarn", "bun"} and runs_test_script:
        return True
    if binary == "go" and args[:1] == ["test"]:
        return True
    if binary == "cargo" and args[:1] in (["test"], ["nextest"]):
        return True
    return binary == "hatch" and args[:1] == ["test"]


def find_test_command(command: str) -> str | None:
    """Return the test-runner part of a command, if one is present.

    Output redirection (`> log 2>&1`) and piping into a logger (`| tee log`)
    are fine. Display text such as `echo pytest` is not a test run. Commands the
    parser cannot model fall back to the legacy substring heuristic.
    """
    operations = split_operations(command)
    if operations is None:
        return command if any(r in command for r in _LEGACY_TEST_RUNNERS) else None
    for operation in operations:
        if operation.kind != "display" and _is_test_words(list(operation.words)):
            return operation.text
    return None


def exit_status(tool_response: object) -> int | None:
    """Extract an exit status from a hook payload's tool response, if present."""
    if not isinstance(tool_response, dict):
        return None
    for key in ("exit_code", "exitCode", "returncode", "return_code", "exit_status"):
        value = tool_response.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def outcome(*, failed_event: bool, tool_response: object) -> str:
    """passed | failed | completed (ran, result not reported by the agent)."""
    if failed_event:
        return "failed"
    status = exit_status(tool_response)
    if status is None:
        return "completed"
    return "passed" if status == 0 else "failed"


def git_head(repo: str) -> str | None:
    """Read HEAD without running git (hook path must stay fast)."""
    try:
        git = Path(repo) / ".git"
        if git.is_file():
            pointer = git.read_text().strip()
            if not pointer.startswith("gitdir:"):
                return None
            git = (Path(repo) / pointer.split(":", 1)[1].strip()).resolve()
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref:"):
            return head if re.fullmatch(r"[0-9a-f]{40}", head) else None
        ref = head.split(":", 1)[1].strip()
        common = git
        commondir = git / "commondir"
        if commondir.is_file():
            common = (git / commondir.read_text().strip()).resolve()
        for base in (git, common):
            ref_file = base / ref
            if ref_file.is_file():
                return ref_file.read_text().strip()
        packed = common / "packed-refs"
        if packed.is_file():
            for line in packed.read_text().splitlines():
                if line.endswith(" " + ref):
                    return line.split(" ", 1)[0]
    except OSError:
        return None
    return None


def write_receipt(
    kind: str,
    *,
    command: str,
    exit_code: int | None,
    repo: str,
    producer: str = "agentlint",
) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown receipt kind '{kind}'")
    directory = receipts_dir()
    directory.mkdir(parents=True, exist_ok=True)
    receipt = {
        "v": 1,
        "kind": kind,
        "command": command[:500],
        "exit_code": exit_code,
        "repo": str(Path(repo).resolve()),
        "git_sha": git_head(repo),
        "created_at": datetime.now(UTC).isoformat(),
        "producer": producer,
    }
    target = directory / f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.json"
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(receipt, sort_keys=True))
    os.replace(tmp, target)
    return target


def _parse_age(value: object) -> float:
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    if isinstance(value, str):
        match = re.fullmatch(r"(\d+)([smhd])", value.strip())
        if match:
            return int(match.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[match.group(2)]
    return float(DEFAULT_MAX_AGE_S)


def find_receipts(
    repo: str,
    *,
    kind: str | None = None,
    since: float | None = None,
    extra_dirs: list[str] | None = None,
    max_age: object = None,
    now: float | None = None,
) -> list[dict]:
    """Valid receipts for this repo, newest first. Mismatched HEADs are excluded."""
    now = now or time.time()
    oldest = now - _parse_age(max_age)
    repo_path = str(Path(repo).resolve())
    head = git_head(repo)
    found: list[dict] = []
    for directory in [receipts_dir(), *(Path(d).expanduser() for d in extra_dirs or [])]:
        try:
            files = sorted(directory.glob("*.json"))[-500:]
        except OSError:
            continue
        for path in files:
            try:
                data = json.loads(path.read_text())
                created = datetime.fromisoformat(data["created_at"]).timestamp()
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                continue
            if (
                not isinstance(data, dict)
                or data.get("v") != 1
                or data.get("kind") not in KINDS
                or (kind and data["kind"] != kind)
                or data.get("repo") != repo_path
                or created < oldest
                or (since is not None and created < since)
                or (data.get("git_sha") and head and data["git_sha"] != head)
                or (isinstance(data.get("exit_code"), int) and data["exit_code"] != 0)
            ):
                continue
            found.append({**data, "_created_ts": created, "_path": str(path)})
    return sorted(found, key=lambda r: r["_created_ts"], reverse=True)


def describe(receipt: dict) -> str:
    label = LEVEL_LABELS.get(str(receipt.get("kind")), str(receipt.get("kind", "evidence")))
    result = (
        "passed"
        if receipt.get("exit_code") == 0
        else "completed, result not reported"
        if receipt.get("exit_code") is None
        else f"exit {receipt.get('exit_code')}"
    )
    when = datetime.fromtimestamp(receipt["_created_ts"], UTC).strftime("%Y-%m-%d %H:%M UTC")
    sha = (receipt.get("git_sha") or "")[:8]
    return f"{label}: `{receipt.get('command', '')}` {result} at {when}" + (
        f" @ {sha}" if sha else ""
    )
