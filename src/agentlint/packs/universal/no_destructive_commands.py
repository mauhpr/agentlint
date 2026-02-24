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

# Protected git branches.
_PROTECTED_BRANCHES = {"main", "master", "develop", "production", "release"}

_RM_RF_RE = re.compile(r"\brm\s+-[^\s]*r[^\s]*f|\brm\s+-[^\s]*f[^\s]*r", re.IGNORECASE)
_DROP_TABLE_RE = re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE)
_DROP_DB_RE = re.compile(r"\bDROP\s+DATABASE\b", re.IGNORECASE)
_GIT_RESET_HARD_RE = re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE)
_GIT_CLEAN_RE = re.compile(r"\bgit\s+clean\s+-fd\b", re.IGNORECASE)

# Catastrophic rm patterns — always ERROR.
_RM_ROOT_RE = re.compile(r"\brm\s+-[^\s]*r[^\s]*f\s+/(?:\s|$)|\brm\s+-[^\s]*f[^\s]*r\s+/(?:\s|$)")
_RM_HOME_RE = re.compile(
    r"\brm\s+-[^\s]*(?:rf|fr)\s+(?:~|\$HOME)(?:\s|/|$)",
    re.IGNORECASE,
)

# New patterns.
_CHMOD_777_RE = re.compile(r"\bchmod\s+(?:-R\s+)?777\b", re.IGNORECASE)
_MKFS_RE = re.compile(r"\bmkfs\b", re.IGNORECASE)
_DD_ZERO_RE = re.compile(r"\bdd\b.*\bif=/dev/zero\b", re.IGNORECASE)
_FORK_BOMB_RE = re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;|\./:0\b")
_DOCKER_PRUNE_RE = re.compile(r"\bdocker\s+system\s+prune\s+-a\b.*--volumes\b|\bdocker\s+system\s+prune\b.*-a\b.*--volumes\b", re.IGNORECASE)
_KUBECTL_DELETE_NS_RE = re.compile(r"\bkubectl\s+delete\s+namespace\b", re.IGNORECASE)
_GIT_BRANCH_DELETE_RE = re.compile(r"\bgit\s+branch\s+-D\s+(\S+)", re.IGNORECASE)


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

    return all(os.path.basename(t.strip("'\"").rstrip("/")) in _SAFE_RM_TARGETS for t in targets)


def _is_catastrophic_rm(command: str) -> bool:
    """Return True if rm -rf targets root, home, or $HOME."""
    return bool(_RM_ROOT_RE.search(command) or _RM_HOME_RE.search(command))


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

        # Catastrophic rm -rf targets (ERROR severity).
        if _RM_RF_RE.search(command) and _is_catastrophic_rm(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Catastrophic command detected: rm -rf on root or home directory",
                    severity=Severity.ERROR,
                    suggestion="This would destroy critical system or user files. Never run rm -rf on / or ~.",
                )
            )
        elif _RM_RF_RE.search(command) and not _rm_targets_safe(command):
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

        # chmod 777 — overly permissive.
        if _CHMOD_777_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Overly permissive command detected: chmod 777",
                    severity=self.severity,
                    suggestion="Use more restrictive permissions (e.g. chmod 755 for dirs, 644 for files).",
                )
            )

        # mkfs — filesystem formatting (ERROR).
        if _MKFS_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Catastrophic command detected: mkfs (filesystem format)",
                    severity=Severity.ERROR,
                    suggestion="mkfs will destroy all data on the target device.",
                )
            )

        # dd if=/dev/zero — disk wiping (ERROR).
        if _DD_ZERO_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Catastrophic command detected: dd if=/dev/zero (disk wipe)",
                    severity=Severity.ERROR,
                    suggestion="dd if=/dev/zero will overwrite data irreversibly.",
                )
            )

        # Fork bomb detection (ERROR).
        if _FORK_BOMB_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Fork bomb detected",
                    severity=Severity.ERROR,
                    suggestion="This command will exhaust system resources.",
                )
            )

        # docker system prune -a --volumes.
        if _DOCKER_PRUNE_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Destructive command detected: docker system prune -a --volumes",
                    severity=self.severity,
                    suggestion="This removes all unused containers, images, networks, and volumes.",
                )
            )

        # kubectl delete namespace.
        if _KUBECTL_DELETE_NS_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Destructive command detected: kubectl delete namespace",
                    severity=self.severity,
                    suggestion="Verify you are not targeting a production namespace.",
                )
            )

        # git branch -D on protected branches.
        branch_match = _GIT_BRANCH_DELETE_RE.search(command)
        if branch_match:
            branch_name = branch_match.group(1).lower()
            if branch_name in _PROTECTED_BRANCHES:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Destructive command detected: git branch -D {branch_match.group(1)}",
                        severity=Severity.ERROR,
                        suggestion=f"Deleting the '{branch_match.group(1)}' branch is dangerous. Use a feature branch instead.",
                    )
                )

        return violations
