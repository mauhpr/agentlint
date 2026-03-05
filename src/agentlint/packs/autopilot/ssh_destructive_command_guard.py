"""Rule: warn on destructive commands executed via SSH on remote servers."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Two-stage detection: first confirm the command involves SSH, then check for
# destructive subcommands.  Each tuple: (compiled_regex, label, severity).
# ERROR = can brick/destroy a machine; WARNING = disruptive but recoverable.
_DESTRUCTIVE_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    (re.compile(r"\brm\s+(?:-r(?:f)?|-f?r|--recursive)\b", re.I), "rm -rf (recursive delete)", Severity.WARNING),
    (re.compile(r"\bdpkg\s+--purge\b", re.I), "dpkg --purge", Severity.WARNING),
    (re.compile(r"\bapt\s+(?:purge|remove)\b", re.I), "apt purge/remove", Severity.WARNING),
    (re.compile(r"\bmkfs\b", re.I), "mkfs (format filesystem)", Severity.ERROR),
    (re.compile(r"\bdd\s+if=", re.I), "dd if= (raw disk write)", Severity.ERROR),
    (re.compile(r"\bsystemctl\s+(?:stop|disable)\b", re.I), "systemctl stop/disable", Severity.WARNING),
    (re.compile(r"\breboot\b", re.I), "reboot", Severity.WARNING),
    (re.compile(r"\bshutdown\b", re.I), "shutdown", Severity.WARNING),
    (re.compile(r"\bpoweroff\b", re.I), "poweroff", Severity.WARNING),
    (re.compile(r"\bhalt\b", re.I), "halt", Severity.WARNING),
    (re.compile(r"\bkill\s+-9\b", re.I), "kill -9", Severity.WARNING),
    (re.compile(r"\bkillall\b", re.I), "killall", Severity.WARNING),
    (re.compile(r"\biptables\s+-F\b", re.I), "iptables -F (flush rules)", Severity.ERROR),
    (re.compile(r"\bterraform\s+destroy\b", re.I), "terraform destroy", Severity.ERROR),
]

_SSH_PREFIX = re.compile(r"\bssh\b", re.I)


class SshDestructiveCommandGuard(Rule):
    """Warn on destructive commands executed via SSH on remote servers."""

    id = "ssh-destructive-command-guard"
    description = "Detects destructive commands (rm -rf, mkfs, reboot, etc.) run via SSH"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        if not _SSH_PREFIX.search(command):
            return []

        rule_config = context.config.get(self.id, {})
        allowed_ops: list[str] = rule_config.get("allowed_ops", [])

        for pattern, label, sev in _DESTRUCTIVE_PATTERNS:
            if label in allowed_ops:
                continue
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Destructive command via SSH: {label}",
                        severity=sev,
                        suggestion=(
                            "Running destructive commands on remote servers via SSH has a high blast "
                            "radius — you cannot physically access the machine to recover. "
                            "Review carefully and run manually after human approval. "
                            "Add to ssh-destructive-command-guard.allowed_ops in agentlint.yml to permanently allow."
                        ),
                    )
                ]

        return []
