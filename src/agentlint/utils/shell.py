"""Conservative recognition of simple commands; never execute or expand shell input.

Unsupported syntax keeps the original text for the existing guards. In particular,
interpreter/SSH bodies, pipelines, redirections and substitutions are not exempted.
"""

from __future__ import annotations

import shlex


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
    if words and words[0] in {"echo", "printf", "/bin/echo", "/usr/bin/printf"}:
        return words[0]
    return command


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
    words = simple_words(command)
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
    return any(tuple(positional[: len(operation)]) == operation for operation in reads)
