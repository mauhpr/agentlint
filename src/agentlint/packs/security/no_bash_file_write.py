"""Rule: block file writes via Bash that bypass Write/Edit guardrails."""

from __future__ import annotations

import ast
import re
from fnmatch import fnmatch
from pathlib import PurePosixPath

from agentlint.config import get_rule_setting
from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Parse only literal, simple Python invocations. Shell expansion/compound commands
# retain the conservative text check; this never executes Python or imports modules.
_PYTHON_BINARY = re.compile(r"python(?:[23](?:\.\d+)?)?$")
_PYTHON_FLAGS = {"-B", "-E", "-I", "-O", "-OO", "-q", "-s", "-S", "-u"}
_WRITE_METHODS = {
    "write",
    "write_text",
    "write_bytes",
    "writelines",
    "truncate",
    "touch",
    "mkdir",
    "unlink",
    "rmdir",
    "rename",
    "replace",
    "chmod",
    "symlink_to",
    "hardlink_to",
}
_OPAQUE_CALLS = {"eval", "exec", "compile", "getattr", "__import__"}
# Unknown interpreter flags and attached -c arguments do not gain read exemptions.
_PYTHON_WRITE_TEXT = re.compile(
    r"\bpython(?:[23](?:\.\d+)?)?\s+(?:(?!-c)\S+\s+)*-c\s*.*"
    r"(?:\b(?:open|Path)\b|\b(?:" + "|".join(sorted(_WRITE_METHODS | _OPAQUE_CALLS)) + r")\s*\()",
    re.DOTALL,
)


def _python_file_write(command: str) -> bool:
    """Detect visible writes without treating path construction/reads as writes.

    This is a syntax check, not proof that arbitrary imported functions are pure.
    Unknown open modes and dynamic execution remain conservative. Unsupported
    shell syntax keeps the previous text-based detection.
    """
    from agentlint.utils.shell import simple_words, unwrap_simple_command

    fallback = bool(_PYTHON_WRITE_TEXT.search(command))
    parsed = simple_words(command)
    words = unwrap_simple_command(parsed) if parsed else None
    if not words or not _PYTHON_BINARY.fullmatch(PurePosixPath(words[0]).name):
        return fallback
    index = 1
    while index < len(words) and words[index] in _PYTHON_FLAGS:
        index += 1
    if index + 1 >= len(words) or words[index] != "-c":
        return fallback
    source = words[index + 1]
    if len(source) > 64 * 1024:
        return fallback
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return fallback

    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                aliases[name.asname or name.name] = name.name
        elif isinstance(node, ast.ImportFrom):
            for name in node.names:
                aliases[name.asname or name.name] = f"{node.module}.{name.name}"

    def name_of(node: ast.expr) -> str:
        attributes: list[str] = []
        while isinstance(node, ast.Attribute):
            attributes.append(node.attr)
            node = node.value
        base = aliases.get(node.id, node.id) if isinstance(node, ast.Name) else ""
        return ".".join([base, *reversed(attributes)])

    called_functions = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    for node in ast.walk(tree):
        # An opener or dynamic execution function passed/assigned elsewhere cannot
        # have its eventual arguments checked (save = open; save(path, 'w')).
        if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
            leaf = (
                node.attr
                if isinstance(node, ast.Attribute)
                else aliases.get(node.id, node.id).rsplit(".", 1)[-1]
            )
            if id(node) not in called_functions and leaf in {"open", *_OPAQUE_CALLS}:
                return True
        # Include method references: save = path.write_text; save(...) writes too.
        if isinstance(node, ast.Attribute) and node.attr in _WRITE_METHODS:
            return True
        if not isinstance(node, ast.Call):
            continue
        name = name_of(node.func)
        leaf = name.rsplit(".", 1)[-1]
        if leaf in _WRITE_METHODS:
            return True
        if leaf in _OPAQUE_CALLS:
            return True
        if leaf != "open":
            continue
        # builtins/io open take (file, mode); pathlib/handle.open take (mode).
        # os.open uses integer flags, so cannot qualify as a proven read here.
        mode_index = 1 if name in {"open", "builtins.open", "io.open", "os.open"} else 0
        if name == "os.open":
            return True
        if any(isinstance(arg, ast.Starred) for arg in node.args) or any(
            keyword.arg is None for keyword in node.keywords
        ):
            return True
        mode = next((kw.value for kw in node.keywords if kw.arg == "mode"), None)
        if mode is None and len(node.args) > mode_index:
            mode = node.args[mode_index]
        if mode is not None and not (
            isinstance(mode, ast.Constant) and mode.value in ("r", "rb", "rt", "br", "tr")
        ):
            return True
    return False


# Default safe patterns — narrow idioms that are not security-relevant.
# Only echo >> (append) to config dotfiles. NOT > (overwrite), NOT cat/tee/sed.
_DEFAULT_SAFE_PATTERNS = [
    r"^\s*echo\s+.*>>\s*\.(?:git|docker|npm|eslint|prettier)ignore\s*$",
]

# --- File-write patterns in Bash commands ---
# Each tuple: (compiled_regex, human-readable label).
_WRITE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # cat/echo/printf redirecting to a file.
    # Negative lookbehind excludes fd redirects like 2>/dev/null.
    (re.compile(r"\b(?:cat|echo|printf)\b.*(?<!\d)>{1,2}\s*(\S+)"), "redirect (>/>>)"),
    # tee writing to a file.
    (re.compile(r"\btee\s+(?:-a\s+)?(\S+)"), "tee"),
    # sed -i (in-place edit).
    (re.compile(r"\bsed\s+(?:.*\s)?-i\s"), "sed -i"),
    # cp — copying to a target (exclude git cp).
    (re.compile(r"(?<!\bgit )\bcp\s+\S+\s+(\S+)"), "cp"),
    # mv — moving to a target (exclude git mv which is a VCS rename).
    (re.compile(r"(?<!\bgit )\bmv\s+\S+\s+(\S+)"), "mv"),
    # perl -pi -e (in-place edit).
    (re.compile(r"\bperl\s+.*-[a-zA-Z]*p[a-zA-Z]*i"), "perl -pi -e"),
    # awk outputting to a file (exclude fd redirects).
    (re.compile(r"\bawk\b.*(?<!\d)>\s*(\S+)"), "awk >"),
    # dd of= (output file).
    (re.compile(r"\bdd\b.*\bof=(\S+)"), "dd of="),
    # Python is inspected separately so Path(...) and read-only open(...) are allowed.
    (_PYTHON_WRITE_TEXT, "python -c write"),
    # Heredoc: cat << EOF > file or cat > file << EOF.
    (re.compile(r"\bcat\b.*<<\s*['\"\\]?\w+"), "heredoc"),
]

# Command substitution heredocs: $(cat <<'EOF' ...) used for passing
# multi-line strings as arguments (e.g. git commit -m, gh pr create --body).
# These are NOT file writes and should be excluded.
_HEREDOC_CMD_SUB = re.compile(r"\$\(\s*cat\s+<<")

# Patterns that extract the target file path from a command.
_TARGET_EXTRACTORS: list[re.Pattern[str]] = [
    # echo/cat/printf ... > file (exclude fd redirects like 2>/dev/null)
    re.compile(r"(?<!\d)>{1,2}\s*(\S+)"),
    # tee file
    re.compile(r"\btee\s+(?:-a\s+)?(\S+)"),
    # cp src dest (exclude git cp)
    re.compile(r"(?<!\bgit )\bcp\s+\S+\s+(\S+)"),
    # mv src dest (exclude git mv)
    re.compile(r"(?<!\bgit )\bmv\s+\S+\s+(\S+)"),
    # dd of=file
    re.compile(r"\bdd\b.*\bof=(\S+)"),
    # sed -i '' 's/old/new/' filename (macOS) or sed -i 's/old/new/' filename (Linux)
    re.compile(r"\bsed\s+(?:.*\s)?-i\s*(?:''?\s+)?(?:'[^']*'\s+|\"[^\"]*\"\s+)?(\S+)\s*$"),
]


def _extract_target_paths(command: str) -> list[str]:
    """Extract target file paths from a Bash command."""
    paths: list[str] = []
    for pattern in _TARGET_EXTRACTORS:
        for match in pattern.finditer(command):
            path = match.group(1).strip("'\"")
            if path:
                paths.append(path)
    return paths


def _path_allowed(
    path: str,
    allow_paths: list[str],
    safe_path_prefixes: list[str] | None = None,
) -> bool:
    """Return True if path is safe-by-default or matches any allow_paths glob.

    Paths under known ephemeral/scratch prefixes (``/tmp/``, ``/var/folders/``
    by default; extended via ``safe_path_prefixes``) are always considered
    allowed since they are scratch space, not project source files.
    """
    from agentlint.utils.paths import is_safe_path

    if is_safe_path(path, extra_prefixes=safe_path_prefixes):
        return True
    return any(fnmatch(path, pattern) for pattern in allow_paths)


def _command_allowed(command: str, allow_patterns: list[str]) -> bool:
    """Return True if command matches any allow_patterns regex."""
    return any(re.search(pattern, command) for pattern in allow_patterns)


class NoBashFileWrite(Rule):
    """Block file writes via Bash that bypass Write/Edit guardrails."""

    id = "no-bash-file-write"
    description = "Blocks file writes via Bash (cat >, tee, sed -i, cp, heredocs, etc.)"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "security"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        # Strip quoted string arguments to avoid false positives on content
        # like: gh pr create --body "... cat > file ..."
        from agentlint.utils.bash import KNOWN_CLI_TOOLS, get_command_binary, strip_string_args

        stripped = strip_string_args(command)

        # Skip known cloud/infra CLI tools — their subcommands (cp, mv)
        # are not shell file operations
        rule_config = context.config.get(self.id, {}) if context.config else {}
        safe_binaries = set(rule_config.get("safe_binaries", []))
        binary = get_command_binary(command)
        if binary in KNOWN_CLI_TOOLS or binary in safe_binaries:
            return []

        # Load config.
        allow_patterns: list[str] = get_rule_setting(context.config, self.id, "allow_patterns", [])
        allow_paths: list[str] = get_rule_setting(context.config, self.id, "allow_paths", [])
        safe_path_prefixes: list[str] = get_rule_setting(
            context.config, self.id, "safe_path_prefixes", []
        )
        strict_mode: bool = get_rule_setting(context.config, self.id, "strict_mode", False)

        # Merge default safe patterns unless strict mode is on.
        effective_patterns = (
            allow_patterns if strict_mode else _DEFAULT_SAFE_PATTERNS + allow_patterns
        )

        # Check if the entire command is whitelisted.
        if effective_patterns and _command_allowed(command, effective_patterns):
            return []

        violations: list[Violation] = []

        for pattern, label in _WRITE_PATTERNS:
            # Python code lives in quoted arguments; inspect syntax, never execute it.
            matched = (
                _python_file_write(command)
                if label == "python -c write"
                else bool(pattern.search(stripped))
            )
            if matched:
                # Heredocs inside $(cat <<'EOF' ...) are command substitution
                # (e.g. git commit -m, gh pr create --body), not file writes.
                if label == "heredoc" and _HEREDOC_CMD_SUB.search(command):
                    continue

                # Check if all target paths are in allowed paths.
                # A shell redirect is not the destination of a Python file write.
                # Python destinations are not extracted, so path exemptions cannot apply.
                target_paths = [] if label == "python -c write" else _extract_target_paths(command)

                # /dev/null is never a real file write.
                target_paths = [p for p in target_paths if p != "/dev/null"]
                if not target_paths and label == "redirect (>/>>)":
                    continue

                # Targets may be allowed by either:
                # - an explicit allow_paths glob, OR
                # - sitting under a default/extra ephemeral safe path
                #   prefix (/tmp/, /var/folders/, ...).
                # Skip the violation if every target satisfies one of these.
                if target_paths and all(
                    _path_allowed(p, allow_paths, safe_path_prefixes) for p in target_paths
                ):
                    continue

                file_path = target_paths[0] if target_paths else None
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Bash file write detected via {label}",
                        severity=self.severity,
                        file_path=file_path,
                        suggestion="Use the Write or Edit tool instead of writing files through Bash.",
                    )
                )
                # One violation per command is sufficient.
                break

        return violations
