"""Rule: block file writes via Bash that bypass Write/Edit guardrails."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, replace
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
_OPAQUE_CALLS = {"eval", "exec", "compile", "getattr", "__import__", "globals", "locals", "vars"}
_OPAQUE_ACCESS = {"__builtins__", "__dict__"}
_QUALIFIED_UNSAFE_CALLS = {
    "os.remove",
    "os.makedirs",
    "os.removedirs",
    "os.symlink",
    "os.link",
    "shutil.copy",
    "shutil.copy2",
    "shutil.copyfile",
    "shutil.copytree",
    "shutil.move",
    "shutil.rmtree",
    "os.system",
    "os.popen",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
}
_QUALIFIED_UNSAFE_LEAVES = {name.rsplit(".", 1)[-1] for name in _QUALIFIED_UNSAFE_CALLS}
# Unknown interpreter flags and attached -c arguments do not gain read exemptions.
_PYTHON_WRITE_TEXT = re.compile(
    r"\bpython(?:[23](?:\.\d+)?)?\s+(?:(?!-c)\S+\s+)*-c\s*.*"
    r"(?:\b(?:open|Path|__builtins__|__dict__|os|shutil|subprocess)\b|\b(?:"
    + "|".join(sorted(_WRITE_METHODS | _OPAQUE_CALLS))
    + r")\s*\()",
    re.DOTALL,
)


@dataclass(frozen=True)
class _PythonFinding:
    kind: str
    expression: str
    line: int | None = None
    column: int | None = None


def _python_finding(command: str) -> _PythonFinding | None:
    """Detect visible writes without treating path construction/reads as writes.

    This is a syntax check, not proof that arbitrary imported functions are pure.
    Unknown open modes and dynamic execution remain conservative. Unsupported
    shell syntax keeps the previous text-based detection.
    """
    from agentlint.utils.shell import split_operations, unwrap_simple_command

    fallback = bool(_PYTHON_WRITE_TEXT.search(command))
    operations = split_operations(command)
    words = (
        unwrap_simple_command(list(operations[0].words))
        if operations and len(operations) == 1
        else None
    )
    opaque = _PythonFinding("unknown", "unsupported Python or shell syntax") if fallback else None
    if not words or not _PYTHON_BINARY.fullmatch(PurePosixPath(words[0]).name):
        return opaque
    index = 1
    while index < len(words) and words[index] in _PYTHON_FLAGS:
        index += 1
    if index + 1 >= len(words) or words[index] != "-c":
        return opaque
    source = words[index + 1]
    if len(source) > 64 * 1024:
        return opaque
    return _python_source_finding(source, fallback=fallback)


def _python_source_finding(source: str, *, fallback: bool = True) -> _PythonFinding | None:
    """Inspect Python source only; never execute it or resolve imports."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return _PythonFinding("unknown", "unparseable Python source") if fallback else None

    aliases: dict[str, str] = {}
    import_bindings: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                aliases[name.asname or name.name] = name.name
                binding = name.asname or name.name
                import_bindings[binding] = import_bindings.get(binding, 0) + 1
        elif isinstance(node, ast.ImportFrom):
            for name in node.names:
                aliases[name.asname or name.name] = f"{node.module}.{name.name}"
                binding = name.asname or name.name
                import_bindings[binding] = import_bindings.get(binding, 0) + 1

    def name_of(node: ast.expr) -> str:
        attributes: list[str] = []
        while isinstance(node, ast.Attribute):
            attributes.append(node.attr)
            node = node.value
        base = aliases.get(node.id, node.id) if isinstance(node, ast.Name) else ""
        return ".".join([base, *reversed(attributes)])

    called_functions = {id(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    rebound = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del)
    }
    rebound.update(node.arg for node in ast.walk(tree) if isinstance(node, ast.arg))
    rebound.update(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    )
    rebound.update(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and node.name
    )
    safe_subprocess = set()
    subprocess_hazard = None
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call) or name_of(call.func) != "subprocess.run":
            continue
        root = call.func
        while isinstance(root, ast.Attribute):
            root = root.value
        if (
            not isinstance(root, ast.Name)
            or root.id in rebound
            or import_bindings.get(root.id) != 1
        ):
            continue
        if subprocess_hazard is None:
            subprocess_hazard = any(
                isinstance(node, ast.Call)
                and name_of(node.func) in {"setattr", "delattr"}
                or isinstance(node, ast.Subscript)
                and isinstance(node.ctx, ast.Store | ast.Del)
                and name_of(node.value) == "os.environ"
                or isinstance(node, ast.Attribute)
                and isinstance(node.ctx, ast.Store | ast.Del)
                and (name_of(node) == "os.environ" or name_of(node).startswith("subprocess."))
                or isinstance(node, ast.Call)
                and name_of(node.func)
                in {
                    "os.putenv",
                    "os.unsetenv",
                    "os.environ.update",
                    "os.environ.clear",
                    "os.environ.pop",
                    "os.environ.setdefault",
                }
                for node in ast.walk(tree)
            )
        if subprocess_hazard:
            continue
        if len(call.args) != 1 or not isinstance(call.args[0], ast.List | ast.Tuple):
            continue
        args = call.args[0].elts
        if len(args) != 4 or not all(
            isinstance(arg, ast.Constant) and isinstance(arg.value, str) for arg in args
        ):
            continue
        values = [arg.value for arg in args]
        if values[:3] != ["git", "cat-file", "-e"] or not re.fullmatch(
            r"[A-Za-z0-9_][A-Za-z0-9_./:@{}~^+-]*", values[3]
        ):
            continue
        if not all(
            isinstance(kw.value, ast.Constant)
            and (
                kw.arg in {"check", "capture_output", "text"}
                and isinstance(kw.value.value, bool)
                or kw.arg == "shell"
                and kw.value.value is False
                or kw.arg == "timeout"
                and isinstance(kw.value.value, int | float)
                and not isinstance(kw.value.value, bool)
                and kw.value.value > 0
            )
            for kw in call.keywords
        ):
            continue
        safe_subprocess.add(id(call.func))

    def expression(node: ast.AST, depth: int = 0) -> str:
        # Preserve the callee, never echo command values or string contents.
        if depth > 20:
            return "..."
        if isinstance(node, ast.Call):
            return expression(node.func, depth + 1) + "(...)"
        if isinstance(node, ast.Attribute):
            return expression(node.value, depth + 1) + "." + node.attr
        if isinstance(node, ast.Name):
            return node.id
        return "..."

    def finding(node: ast.AST, kind: str = "unknown") -> _PythonFinding:
        return _PythonFinding(kind, expression(node), node.lineno, node.col_offset + 1)

    def string_replace(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "replace"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, (str, bytes))
        )

    def mutation_kind(node: ast.AST) -> str:
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Call)
            and name_of(node.value.func)
            in {"pathlib.Path", "pathlib.PosixPath", "pathlib.WindowsPath"}
        ):
            return "write"
        return "unknown"

    for node in ast.walk(tree):
        # An opener or dynamic execution function passed/assigned elsewhere cannot
        # have its eventual arguments checked (save = open; save(path, 'w')).
        if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
            leaf = (
                node.attr
                if isinstance(node, ast.Attribute)
                else aliases.get(node.id, node.id).rsplit(".", 1)[-1]
            )
            if leaf in _OPAQUE_ACCESS:
                return finding(node)
            if leaf in _QUALIFIED_UNSAFE_LEAVES and name_of(node) in _QUALIFIED_UNSAFE_CALLS:
                if id(node) in safe_subprocess:
                    continue
                kind = (
                    "unknown"
                    if id(node) not in called_functions
                    or leaf
                    in {"system", "popen", "run", "call", "check_call", "check_output", "Popen"}
                    else "write"
                )
                return finding(node, kind)
            if id(node) not in called_functions and leaf in {"open", *_OPAQUE_CALLS}:
                return finding(node)
        # Calling a string-keyed opener bypasses normal mode inspection. Ordinary
        # data reads such as payload['open'] are not callable builtin lookups.
        if (
            isinstance(node, ast.Subscript)
            and id(node) in called_functions
            and isinstance(node.slice, ast.Constant)
            and node.slice.value in ("open", *_OPAQUE_CALLS)
        ):
            return finding(node)
        # Include method references: save = path.write_text; save(...) writes too.
        if isinstance(node, ast.Attribute) and node.attr in _WRITE_METHODS:
            if string_replace(node):
                continue
            return finding(node, mutation_kind(node) if id(node) in called_functions else "unknown")
        if not isinstance(node, ast.Call):
            continue
        name = name_of(node.func)
        leaf = name.rsplit(".", 1)[-1]
        if leaf in _WRITE_METHODS:
            if string_replace(node.func):
                continue
            return finding(node, mutation_kind(node.func))
        if leaf in _OPAQUE_CALLS:
            return finding(node)
        if leaf != "open":
            continue
        # builtins/io open take (file, mode); pathlib/handle.open take (mode).
        # os.open uses integer flags, so cannot qualify as a proven read here.
        mode_index = 1 if name in {"open", "builtins.open", "io.open", "os.open"} else 0
        if name == "os.open":
            return finding(node)
        if any(isinstance(arg, ast.Starred) for arg in node.args) or any(
            keyword.arg is None for keyword in node.keywords
        ):
            return finding(node)
        mode = next((kw.value for kw in node.keywords if kw.arg == "mode"), None)
        if mode is None and len(node.args) > mode_index:
            mode = node.args[mode_index]
        if mode is not None and not (
            isinstance(mode, ast.Constant) and mode.value in ("r", "rb", "rt", "br", "tr")
        ):
            known_write = (
                isinstance(mode, ast.Constant)
                and isinstance(mode.value, str)
                and any(flag in mode.value for flag in "wax+")
            )
            kind = (
                "write"
                if known_write
                and (
                    name in {"open", "builtins.open", "io.open"}
                    or mutation_kind(node.func) == "write"
                )
                else "unknown"
            )
            return finding(node, kind)
    return None


def _literal_heredoc(command: str) -> tuple[str, str] | None:
    """Recognize one quoted stdin heredoc with no trailing shell operations.

    Only cat and Python stdin invocations qualify. Quoted delimiters prevent
    shell expansion of the body; everything else keeps conservative matching.
    """
    header, sep, rest = command.partition("\n")
    if not sep:
        return None
    match = re.fullmatch(
        r"\s*(cat|(?:[\w./-]*/)?python(?:[23](?:\.\d+)?)?\s+-)\s*"
        r"<<\s*(['\"])([A-Za-z_][A-Za-z_0-9]*)\2\s*",
        header,
    )
    if not match:
        return None
    lines = rest.splitlines()
    delimiter = match[3]
    if not lines or lines[-1] != delimiter or delimiter in lines[:-1]:
        return None
    return ("cat" if match[1] == "cat" else "python"), "\n".join(lines[:-1])


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
    # Unsupported stdin programs remain conservative; literal quoted bodies
    # are inspected above, and their output redirect is not their write target.
    (re.compile(r"\bpython(?:[23](?:\.\d+)?)?\b[^\n]*<<"), "python stdin heredoc"),
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

        # Keep flags, targets and exemptions within their shell operation.
        from agentlint.utils.shell import split_operations

        operations = split_operations(command)
        if operations and len(operations) > 1:
            for operation in operations:
                violations = self.evaluate(
                    replace(context, tool_input={**context.tool_input, "command": operation.source})
                )
                if violations:
                    return violations
            return []

        heredoc = _literal_heredoc(command)
        if heredoc:
            binary, source = heredoc
            finding = (
                _python_source_finding(source)
                if binary == "python" and len(source) <= 64 * 1024
                else None
            )
            if binary == "cat" or (len(source) <= 64 * 1024 and finding is None):
                return []
            return [
                Violation(
                    rule_id=self.id,
                    message=self._python_message(finding) + " (Python stdin heredoc)",
                    severity=self.severity,
                    line=finding.line if finding else None,
                    operation=finding.expression if finding else "oversized Python stdin heredoc",
                    suggestion="Use apply_patch (Codex) or Write/Edit for file changes; keep stdin Python read-only.",
                )
            ]

        # Strip quoted string arguments to avoid false positives on content
        # like: gh pr create --body "... cat > file ..."
        from agentlint.utils.bash import KNOWN_CLI_TOOLS, get_command_binary, strip_string_args

        stripped = strip_string_args(command)

        rule_config = context.config.get(self.id, {}) if context.config else {}
        safe_binaries = set(rule_config.get("safe_binaries", []))
        binary = get_command_binary(command)

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

        # The shell opens output files independently of the executable's behavior.
        # Neither read-only Python nor a trusted CLI exempts those writes.
        if operations:
            for operator, target in operations[0].redirects:
                redirect = operator.lstrip("0123456789")
                if redirect not in {">", ">>", "&>", "&>>", ">&"}:
                    continue
                if redirect == ">&" and (target.isdigit() or target == "-"):
                    continue
                if target == "/dev/null" or _path_allowed(target, allow_paths, safe_path_prefixes):
                    continue
                return [
                    Violation(
                        rule_id=self.id,
                        message="Bash file write detected via shell output redirect",
                        severity=self.severity,
                        file_path=target,
                        operation="shell output redirect",
                        suggestion="Use apply_patch (Codex) or Write/Edit for maintained files; redirect scratch output to /tmp/.",
                    )
                ]

        # Cloud/infra subcommands (cp, mv) are not local shell file operations.
        if binary == "gcloud" and operations:
            from agentlint.utils.shell import storage_copy_endpoints, unwrap_simple_command

            words = unwrap_simple_command(list(operations[0].words)) or []
            try:
                endpoints = storage_copy_endpoints(words)
            except ValueError:
                return [
                    Violation(
                        rule_id=self.id,
                        severity=self.severity,
                        message="Cannot classify cloud storage copy file effects safely",
                        suggestion="Use an exact source and destination with supported literal flags.",
                    )
                ]
            if endpoints:
                destination = endpoints[-1]
                if not destination.startswith("gs://") and not _path_allowed(
                    destination, allow_paths, safe_path_prefixes
                ):
                    return [
                        Violation(
                            rule_id=self.id,
                            severity=self.severity,
                            file_path=destination,
                            message="Cloud storage copy writes a local file",
                            operation="gcloud storage cp local destination",
                            suggestion="Use a scoped scratch destination or the normal file-edit workflow.",
                        )
                    ]
        if binary in KNOWN_CLI_TOOLS or binary in safe_binaries:
            return []

        violations: list[Violation] = []

        for pattern, label in _WRITE_PATTERNS:
            finding = _python_finding(command) if label == "python -c write" else None
            # Python code lives in quoted arguments; inspect syntax, never execute it.
            matched = (
                finding is not None
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
                target_paths = [] if label.startswith("python") else _extract_target_paths(command)

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
                        message=self._python_message(finding)
                        if finding
                        else f"Bash file write detected via {label}",
                        severity=self.severity,
                        file_path=file_path,
                        line=finding.line if finding else None,
                        operation=finding.expression if finding else label,
                        suggestion=(
                            "Use apply_patch (Codex) or Write/Edit for maintained files. "
                            "For local test logs, use `set -o pipefail && pytest -q 2>&1 | tee /private/tmp/tests.log`. "
                            "For a literal stdin heredoc, quote its delimiter and omit output redirects."
                        ),
                    )
                )
                # One violation per command is sufficient.
                break

        return violations

    @staticmethod
    def _python_message(finding: _PythonFinding | None) -> str:
        if finding is None:
            return "Cannot classify oversized Python source safely"
        reason = (
            "Confirmed Python file write"
            if finding.kind == "write"
            else "Cannot classify Python operation safely"
        )
        location = f" at line {finding.line}, column {finding.column}" if finding.line else ""
        return f"{reason}{location}: {finding.expression}"
