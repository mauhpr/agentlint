"""Rule: warn on cron, systemd, and launchctl mutations that establish persistence."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}
_FILE_TOOLS = {"Write", "Edit", "MultiEdit"}

# Bash patterns that modify schedulers.
_SCHEDULER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Cron — explicit write-intent forms only (-e edit, -r remove, or file install).
    (re.compile(r"\bcrontab\s+-[er]\b", re.I), "crontab modification"),
    (re.compile(r"\bcrontab\s+(?!-)[^\s]", re.I), "crontab file install"),
    (re.compile(r"\becho\b.*\|\s*crontab\b", re.I), "crontab pipe injection"),
    # Systemd.
    (re.compile(r"\bsystemctl\s+(?:enable|disable|mask|unmask|edit)\b", re.I), "systemctl service modification"),
    (re.compile(r"\bsystemctl\s+daemon-reload\b", re.I), "systemctl daemon-reload"),
    # macOS launchctl.
    (re.compile(r"\blaunchctl\s+(?:load|unload|bootstrap|bootout)\b", re.I), "launchctl service modification"),
    # at/batch schedulers.
    (re.compile(r"\bat\s+now\b|\bat\s+\d", re.I), "at scheduler job"),
]

# File paths that indicate scheduler config writes (for Write/Edit tools).
_SCHEDULER_FILE_PREFIXES = (
    "/etc/cron",
    "/var/spool/cron",
    "/etc/systemd/system",
    "/usr/lib/systemd/system",
    "/Library/LaunchDaemons",
    "/Library/LaunchAgents",
)
_SCHEDULER_FILE_HOME = "Library/LaunchAgents"  # ~/Library/LaunchAgents


def _is_scheduler_file(path: str) -> bool:
    """Return True if the file path is a scheduler configuration file."""
    for prefix in _SCHEDULER_FILE_PREFIXES:
        if path.startswith(prefix):
            return True
    # Handle ~/Library/LaunchAgents
    if _SCHEDULER_FILE_HOME in path:
        return True
    return False


class SystemSchedulerGuard(Rule):
    """Warn on cron/systemd/launchctl mutations that establish background persistence."""

    id = "system-scheduler-guard"
    description = "Warns on crontab, systemctl enable/disable, launchctl, and scheduler file writes"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        # Bash command patterns.
        if context.tool_name in _BASH_TOOLS:
            command: str = context.command or ""
            if not command:
                return []
            for pattern, label in _SCHEDULER_PATTERNS:
                if pattern.search(command):
                    return [
                        Violation(
                            rule_id=self.id,
                            message=f"Scheduler mutation detected: {label}",
                            severity=self.severity,
                            suggestion=(
                                "Scheduled tasks established by an agent persist after the session ends. "
                                "Verify this is intentional and the schedule is correct before proceeding."
                            ),
                        )
                    ]

        # File write to scheduler config paths.
        elif context.tool_name in _FILE_TOOLS:
            file_path: str = context.file_path or ""
            if file_path and _is_scheduler_file(file_path):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Writing to scheduler configuration path: {file_path}",
                        severity=self.severity,
                        file_path=file_path,
                        suggestion=(
                            "Scheduler configuration files written by an agent persist after the session ends. "
                            "Verify this is intentional before proceeding."
                        ),
                    )
                ]

        return []
