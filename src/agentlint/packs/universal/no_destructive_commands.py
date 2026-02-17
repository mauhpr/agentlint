"""Rule: warn on destructive shell commands."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Directories that are safe to rm -rf.
_SAFE_RM_TARGETS = {
    "node_modules",
    "__pycache__",
    ".cache",
    "dist",
    "build",
    ".venv",
    ".pytest_cache",
}

_RM_RF_RE = re.compile(r"\brm\s+-[^\s]*r[^\s]*f|\brm\s+-[^\s]*f[^\s]*r", re.IGNORECASE)
_DROP_TABLE_RE = re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE)
_DROP_DB_RE = re.compile(r"\bDROP\s+DATABASE\b", re.IGNORECASE)
_GIT_RESET_HARD_RE = re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE)
_GIT_CLEAN_RE = re.compile(r"\bgit\s+clean\s+-fd\b", re.IGNORECASE)


def _rm_targets_safe(command: str) -> bool:
    """Return True if all rm -rf targets are known safe directories."""
    # Extract everything after rm -rf / rm -fr flags.
    parts = re.split(r"\brm\s+-\S+\s+", command)
    if len(parts) < 2:
        return False

    # Look at the target portion (everything after the flags until a pipe/semicolon/&&).
    target_str = re.split(r"[;&|]", parts[-1])[0].strip()
    targets = target_str.split()

    if not targets:
        return False

    import os

    return all(os.path.basename(t.rstrip("/")) in _SAFE_RM_TARGETS for t in targets)


class NoDestructiveCommands(Rule):
    """Warn on destructive shell commands that may cause data loss."""

    id = "no-destructive-commands"
    description = "Warns on destructive commands like rm -rf, DROP TABLE, git reset --hard"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        violations: list[Violation] = []

        if _RM_RF_RE.search(command) and not _rm_targets_safe(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Destructive command detected: rm -rf",
                    severity=self.severity,
                    suggestion="Double-check the target path before running rm -rf.",
                )
            )

        if _DROP_TABLE_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Destructive command detected: DROP TABLE",
                    severity=self.severity,
                    suggestion="Ensure you have a backup before dropping tables.",
                )
            )

        if _DROP_DB_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Destructive command detected: DROP DATABASE",
                    severity=self.severity,
                    suggestion="Ensure you have a backup before dropping databases.",
                )
            )

        if _GIT_RESET_HARD_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Destructive command detected: git reset --hard",
                    severity=self.severity,
                    suggestion="Consider using git stash instead of git reset --hard.",
                )
            )

        if _GIT_CLEAN_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Destructive command detected: git clean -fd",
                    severity=self.severity,
                    suggestion="Run git clean -n first to preview what will be removed.",
                )
            )

        return violations
