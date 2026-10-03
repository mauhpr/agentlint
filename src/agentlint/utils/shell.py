"""Conservative recognition of simple commands; never execute or expand shell input.

Unsupported syntax keeps the original text for the existing guards. In particular,
interpreter/SSH bodies, pipelines, redirections and substitutions are not exempted.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path


def simple_words(command: str) -> list[str] | None:
    """Return words only when no shell expansion or compound syntax is present."""
    if any(char in command for char in ("$", "`", "\n", "\r", "\x00")):
        return None
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
        lexer.whitespace_split = True
        lexer.commenters = ""
        words = list(lexer)
    except ValueError:
        return None
    if any(word and all(char in ";&|<>()" for char in word) for word in words):
        return None
    return words


def mutation_command(command: str) -> str:
    """Hide literal display arguments from mutation guards, preserving other syntax."""
    words = simple_words(command)
    unwrapped = unwrap_simple_command(words) if words else None
    if unwrapped and unwrapped[0] in {"echo", "printf", "/bin/echo", "/usr/bin/printf"}:
        return unwrapped[0]
    return command


_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*=.*", re.DOTALL)


def unwrap_simple_command(words: list[str]) -> list[str] | None:
    """Strip only literal env/command wrappers; never evaluate shell syntax."""
    words = words[:]
    while words:
        if words[0] == "command":
            words = words[1:]
        elif words[0] in {"env", "/usr/bin/env"}:
            words = words[1:]
            while words and _ASSIGNMENT.fullmatch(words[0]):
                words = words[1:]
            if words and words[0].startswith("-"):
                return None
        else:
            return words
    return None


_GCLOUD_READS = {
    ("run", "services", "describe"),
    ("run", "services", "list"),
    ("run", "jobs", "describe"),
    ("run", "jobs", "list"),
    ("run", "jobs", "executions", "describe"),
    ("run", "jobs", "executions", "list"),
    ("scheduler", "jobs", "describe"),
    ("scheduler", "jobs", "list"),
    ("sql", "instances", "describe"),
    ("sql", "instances", "list"),
    ("compute", "instances", "describe"),
    ("compute", "instances", "list"),
    ("projects", "describe"),
    ("projects", "list"),
    ("artifacts", "docker", "images", "describe"),
}
_AWS_READS = {
    ("sts", "get-caller-identity"),
    ("ec2", "describe-instances"),
    ("rds", "describe-db-instances"),
    ("s3api", "list-buckets"),
}
_VALUE_FLAGS = {
    "--project",
    "--region",
    "--location",
    "--zone",
    "--format",
    "--filter",
    "--limit",
    "--page-size",
    "--sort-by",
    "--account",
    "--profile",
    "--output",
    "--query",
}


def is_readonly_cloud_command(command: str) -> bool:
    """Recognize a narrow set of cloud inspection operations with known flags."""
    parsed = simple_words(command)
    words = unwrap_simple_command(parsed) if parsed else None
    if not words or words[0] not in {"gcloud", "aws"}:
        return False
    positional: list[str] = []
    i = 1
    while i < len(words):
        word = words[i]
        i += 1
        if word.startswith("-"):
            name, equals, value = word.partition("=")
            if name not in _VALUE_FLAGS:
                return False
            if not equals:
                if i == len(words) or words[i].startswith("-"):
                    return False
                i += 1
            elif not value:
                return False
        else:
            positional.append(word)
    reads = _GCLOUD_READS if words[0] == "gcloud" else _AWS_READS
    return any(
        tuple(positional[: len(operation)]) == operation
        and len(positional) == len(operation) + (1 if operation[-1] == "describe" else 0)
        for operation in reads
    )


def is_readonly_psql_command(command: str, project_dir: str) -> bool:
    """Recognize psql scripts explicitly enclosed by a read-only transaction."""
    parsed = simple_words(command)
    words = unwrap_simple_command(parsed) if parsed else None
    if not words or words[0] != "psql":
        return False
    script: str | None = None
    i = 1
    while i < len(words):
        word = words[i]
        i += 1
        if word in {"-h", "-d", "-U", "-p", "--host", "--dbname", "--username", "--port"}:
            if i >= len(words):
                return False
            i += 1
        elif (
            word.startswith("postgresql://")
            or word.startswith("postgres://")
            or word in {"-X", "--no-psqlrc", "-A", "-t", "-q"}
        ):
            continue
        elif word in {"-c", "--command"} and script is None and i < len(words):
            script = words[i]
            i += 1
        elif word in {"-f", "--file"} and script is None and i < len(words):
            path = Path(project_dir, words[i]).resolve()
            i += 1
            try:
                path.relative_to(Path(project_dir).resolve())
                if path.stat().st_size > 64 * 1024:
                    return False
                script = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError, ValueError):
                return False
        else:
            return False
    if script is None or "\\" in script or "--" in script or "/*" in script:
        return False
    statements = [part.strip() for part in script.split(";") if part.strip()]
    if len(statements) < 3 or not re.fullmatch(
        r"BEGIN(?:\s+TRANSACTION)?\s+READ\s+ONLY", statements[0], re.IGNORECASE
    ):
        return False
    if not re.fullmatch(r"(?:COMMIT|ROLLBACK)", statements[-1], re.IGNORECASE):
        return False
    return all(
        re.match(r"^(?:SELECT|SHOW|EXPLAIN\s+SELECT)\b", stmt, re.IGNORECASE)
        and not re.search(r"\b(?:INTO|FOR\s+(?:UPDATE|SHARE))\b", stmt, re.IGNORECASE)
        for stmt in statements[1:-1]
    )
