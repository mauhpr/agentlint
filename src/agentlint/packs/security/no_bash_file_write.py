"""Rule: block file writes via Bash that bypass Write/Edit guardrails."""
from __future__ import annotations

import re
from fnmatch import fnmatch

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# --- File-write patterns in Bash commands ---
# Each tuple: (compiled_regex, human-readable label).
_WRITE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # cat/echo/printf redirecting to a file.
    (re.compile(r"\b(?:cat|echo|printf)\b.*>{1,2}\s*(\S+)"), "redirect (>/>>)"),
    # tee writing to a file.
    (re.compile(r"\btee\s+(?:-a\s+)?(\S+)"), "tee"),
    # sed -i (in-place edit).
    (re.compile(r"\bsed\s+(?:.*\s)?-i\s"), "sed -i"),
    # cp — copying to a target.
    (re.compile(r"\bcp\s+\S+\s+(\S+)"), "cp"),
    # mv — moving to a target.
    (re.compile(r"\bmv\s+\S+\s+(\S+)"), "mv"),
    # perl -pi -e (in-place edit).
    (re.compile(r"\bperl\s+.*-[a-zA-Z]*p[a-zA-Z]*i"), "perl -pi -e"),
    # awk outputting to a file.
    (re.compile(r"\bawk\b.*>\s*(\S+)"), "awk >"),
    # dd of= (output file).
    (re.compile(r"\bdd\b.*\bof=(\S+)"), "dd of="),
    # python -c with open(...).write(...) or pathlib write.
    (re.compile(r"\bpython[23]?\s+-c\s+.*(?:open\s*\(|\.write\s*\(|Path\s*\()"), "python -c write"),
    # Heredoc: cat << EOF > file or cat > file << EOF.
    (re.compile(r"\bcat\b.*<<\s*['\"\\]?\w+"), "heredoc"),
]

# Command substitution heredocs: $(cat <<'EOF' ...) used for passing
# multi-line strings as arguments (e.g. git commit -m, gh pr create --body).
# These are NOT file writes and should be excluded.
_HEREDOC_CMD_SUB = re.compile(r"\$\(\s*cat\s+<<")

# Patterns that extract the target file path from a command.
_TARGET_EXTRACTORS: list[re.Pattern[str]] = [
    # echo/cat/printf ... > file
    re.compile(r">{1,2}\s*(\S+)"),
    # tee file
    re.compile(r"\btee\s+(?:-a\s+)?(\S+)"),
    # cp src dest
    re.compile(r"\bcp\s+\S+\s+(\S+)"),
    # mv src dest
    re.compile(r"\bmv\s+\S+\s+(\S+)"),
    # dd of=file
    re.compile(r"\bdd\b.*\bof=(\S+)"),
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


def _path_allowed(path: str, allow_paths: list[str]) -> bool:
    """Return True if path matches any allow_paths glob pattern."""
    for pattern in allow_paths:
        if fnmatch(path, pattern):
            return True
    return False


def _command_allowed(command: str, allow_patterns: list[str]) -> bool:
    """Return True if command matches any allow_patterns regex."""
    for pattern in allow_patterns:
        if re.search(pattern, command):
            return True
    return False


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

        # Load config.
        rule_config = context.config.get(self.id, {})
        allow_patterns: list[str] = rule_config.get("allow_patterns", [])
        allow_paths: list[str] = rule_config.get("allow_paths", [])

        # Check if the entire command is whitelisted.
        if allow_patterns and _command_allowed(command, allow_patterns):
            return []

        violations: list[Violation] = []

        for pattern, label in _WRITE_PATTERNS:
            if pattern.search(command):
                # Heredocs inside $(cat <<'EOF' ...) are command substitution
                # (e.g. git commit -m, gh pr create --body), not file writes.
                if label == "heredoc" and _HEREDOC_CMD_SUB.search(command):
                    continue

                # Check if all target paths are in allowed paths.
                target_paths = _extract_target_paths(command)
                if allow_paths and target_paths and all(
                    _path_allowed(p, allow_paths) for p in target_paths
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
