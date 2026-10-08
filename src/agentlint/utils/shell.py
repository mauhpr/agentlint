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


# ---------------------------------------------------------------------------
# Parsed operations (v2.9.0)
#
# A deliberately small, quote-aware tokenizer for simple command lists. It never
# expands or executes anything. Any construct it does not fully understand
# (substitutions, subshells, heredocs, unterminated quotes) makes the whole
# command unparseable, and callers fall back to raw-text matching.
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field  # noqa: E402

_CONTROL_OPS = ("&&", "||", ";", "|", "&")
_REDIRECT_RE = re.compile(r"^(\d*)(>>|>&|>|<&|<|&>>|&>)$")


@dataclass(frozen=True)
class Operation:
    """One simple command inside a command list."""

    words: tuple[str, ...]
    redirects: tuple[tuple[str, str], ...] = field(default=())
    kind: str = "mutate"  # display | read | mutate | unknown
    # Exact source text of this operation, so unquoted `~`, globs and quoting
    # keep their original meaning for pattern-based rules.
    source: str = ""

    @property
    def binary(self) -> str:
        return self.words[0].rsplit("/", 1)[-1] if self.words else ""

    @property
    def text(self) -> str:
        return self.source


def _tokenize(command: str) -> list[tuple[str, bool, int, int]] | None:
    """Split into (token, is_operator, start, end); None for unsupported syntax."""
    tokens: list[tuple[str, bool, int, int]] = []
    word: list[str] = []
    in_word = False
    word_start = 0
    i, n = 0, len(command)

    def flush() -> None:
        nonlocal word, in_word
        if in_word:
            tokens.append(("".join(word), False, word_start, i))
        word, in_word = [], False

    def begin() -> None:
        nonlocal in_word, word_start
        if not in_word:
            word_start = i
            in_word = True

    while i < n:
        c = command[i]
        if c in "\x00\r`$(){}":
            return None
        if c == "'":
            end = command.find("'", i + 1)
            if end < 0:
                return None
            begin()
            word.append(command[i + 1 : end])
            i = end + 1
            continue
        if c == '"':
            j = i + 1
            buf: list[str] = []
            while j < n and command[j] != '"':
                ch = command[j]
                if ch in "$`":
                    return None
                if ch == "\\" and j + 1 < n and command[j + 1] in '"\\$`\n':
                    buf.append(command[j + 1])
                    j += 2
                    continue
                buf.append(ch)
                j += 1
            if j >= n:
                return None
            begin()
            word.append("".join(buf))
            i = j + 1
            continue
        if c == "\\":
            if i + 1 >= n:
                return None
            if command[i + 1] != "\n":
                begin()
                word.append(command[i + 1])
            i += 2
            continue
        if c == "#" and not in_word:
            end = command.find("\n", i)
            i = n if end < 0 else end
            continue
        if c == "\n":
            flush()
            tokens.append(("\n", True, i, i + 1))
            i += 1
            continue
        if c in " \t":
            flush()
            i += 1
            continue
        if c in "&|;<>":
            # Attach a numeric file descriptor prefix (2>&1) to the operator.
            fd = ""
            joined = "".join(word)
            op_start = i
            if in_word and c in "<>" and joined.isdigit() and command[i - 1].isdigit():
                fd, word, in_word, op_start = joined, [], False, word_start
            flush()
            for op in ("&>>", ">>", ">&", "<&", "&>", "&&", "||", "<<"):
                if command.startswith(op, i):
                    if op == "<<":
                        return None  # heredocs are not modelled
                    tokens.append((fd + op, True, op_start, i + len(op)))
                    i += len(op)
                    break
            else:
                tokens.append((fd + c, True, op_start, i + 1))
                i += 1
            continue
        begin()
        word.append(c)
        i += 1
    flush()
    return tokens


_READ_BINARIES = {
    "cat",
    "head",
    "tail",
    "less",
    "more",
    "wc",
    "ls",
    "pwd",
    "which",
    "type",
    "sort",
    "uniq",
    "cut",
    "tr",
    "jq",
    "yq",
    "diff",
    "stat",
    "file",
    "tree",
    "grep",
    "egrep",
    "fgrep",
    "rg",
    "ag",
    "date",
    "whoami",
    "basename",
    "dirname",
    "realpath",
    "readlink",
    "true",
    "false",
    "test",
    "[",
    "column",
    "nl",
    "comm",
    "cmp",
    "md5",
    "md5sum",
    "sha256sum",
    "shasum",
    "du",
    "df",
    "env",
    "printenv",
    "uname",
    "hostname",
    "id",
}
_DISPLAY_BINARIES = {"echo", "printf"}
_GIT_READS = {
    "status",
    "log",
    "diff",
    "show",
    "rev-parse",
    "ls-files",
    "ls-tree",
    "grep",
    "blame",
    "describe",
    "shortlog",
    "rev-list",
    "cat-file",
    "merge-base",
    "name-rev",
    "for-each-ref",
}
_GH_READS = {
    ("pr", "view"),
    ("pr", "list"),
    ("pr", "diff"),
    ("pr", "checks"),
    ("pr", "status"),
    ("issue", "view"),
    ("issue", "list"),
    ("run", "list"),
    ("run", "view"),
    ("release", "view"),
    ("release", "list"),
    ("repo", "view"),
}
_FIND_ACTIONS = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"}


def _classify(words: list[str], redirects: list[tuple[str, str]]) -> str:
    unwrapped = unwrap_simple_command(words)
    if not unwrapped:
        return "unknown"
    binary = unwrapped[0].rsplit("/", 1)[-1]
    args = unwrapped[1:]
    writes_file = any(
        op.lstrip("0123456789&") in {">", ">>"} and target != "/dev/null"
        for op, target in redirects
    )
    if binary in _DISPLAY_BINARIES:
        return "display"
    if writes_file:
        return "mutate"
    if binary == "env" and args:
        return "mutate"
    if binary in _READ_BINARIES:
        return "read"
    if binary == "find" and not _FIND_ACTIONS & set(args):
        return "read"
    if binary == "sed" and not any(a.startswith("-i") or a == "--in-place" for a in args):
        return "read"
    if binary == "git":
        sub = next((a for a in args if not a.startswith("-")), "")
        if sub in _GIT_READS:
            return "read"
        if sub == "branch" and not {"-d", "-D", "-m", "-M", "--delete", "--move"} & set(args):
            return "read"
        if sub == "remote" and args[-1:] in (["remote"], ["-v"]):
            return "read"
    if binary == "gh" and tuple(args[:2]) in _GH_READS:
        return "read"
    if is_readonly_cloud_command(" ".join(shlex.quote(w) for w in words)):
        return "read"
    return "mutate"


# Binaries that turn their stdin into commands. Piping data into them means the
# "data" is code, so the command is treated as unparseable (raw-text matching).
_EXEC_SINKS = {
    "sh",
    "bash",
    "zsh",
    "dash",
    "ksh",
    "fish",
    "python",
    "python3",
    "node",
    "perl",
    "ruby",
    "php",
    "xargs",
    "parallel",
    "ssh",
    "eval",
    "source",
    ".",
    "sudo",
    "su",
    "psql",
    "mysql",
    "sqlite3",
    "kubectl",
    "docker",
    "env",
    "exec",
    "nohup",
    "time",
}


def split_operations(command: str) -> list[Operation] | None:
    """Split a simple command list into classified operations.

    Returns None when the command contains syntax that is not fully modelled;
    callers must then keep matching against the raw command text.
    """
    tokens = _tokenize(command)
    if tokens is None:
        return None
    operations: list[Operation] = []
    words: list[str] = []
    redirects: list[tuple[str, str]] = []
    expect_target: str | None = None
    piped = False
    span: list[int] = []

    def close(separator: str) -> bool:
        if not words:
            # Blank lines are fine; an operator with no command before it is not.
            return not redirects and separator == "\n"
        operations.append(
            Operation(
                tuple(words),
                tuple(redirects),
                _classify(list(words), list(redirects)),
                command[span[0] : span[1]],
            )
        )
        return True

    for token, is_op, start, end in tokens:
        if expect_target is not None:
            if is_op:
                return None
            redirects.append((expect_target, token))
            expect_target = None
            span[1] = end
            continue
        if is_op and (token in _CONTROL_OPS or token == "\n"):
            if not close(token):
                return None
            words, redirects, span = [], [], []
            piped = token == "|"
            continue
        if piped and not words:
            if token.rsplit("/", 1)[-1] in _EXEC_SINKS:
                return None
            piped = False
        if not span:
            span = [start, end]
        span[1] = end
        if is_op:
            if not _REDIRECT_RE.match(token):
                return None
            expect_target = token
            continue
        words.append(token)
    if expect_target is not None or not close("\n"):
        return None
    if piped:
        return None
    return operations


def active_operations(command: str) -> list[Operation] | None:
    """Operations that can change state (display/read-only ones removed)."""
    operations = split_operations(command)
    if operations is None:
        return None
    return [op for op in operations if op.kind not in {"display", "read"}]
