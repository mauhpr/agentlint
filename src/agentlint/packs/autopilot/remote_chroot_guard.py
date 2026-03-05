"""Rule: detect risky operations inside a chroot on remote systems."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Each tuple: (compiled_regex, label, severity).
_CHROOT_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    # ERROR: removing bootloader packages inside chroot
    (
        re.compile(r"\bchroot\b.*\bdpkg\s+--purge\b.*\b(?:grub|linux-image|shim-signed)\b", re.I),
        "chroot dpkg --purge bootloader package",
        Severity.ERROR,
    ),
    (
        re.compile(r"\bchroot\b.*\bapt\s+(?:remove|purge)\b.*\b(?:grub|linux-image|shim-signed)\b", re.I),
        "chroot apt remove/purge bootloader package",
        Severity.ERROR,
    ),
    # WARNING: potentially risky repair operations inside chroot
    (
        re.compile(r"\bchroot\b.*\bapt\s+--fix-broken\s+install\b", re.I),
        "chroot apt --fix-broken install",
        Severity.WARNING,
    ),
    (
        re.compile(r"\bchroot\b.*\bdpkg\s+--configure\s+-a\b", re.I),
        "chroot dpkg --configure -a",
        Severity.WARNING,
    ),
]


class RemoteChrootGuard(Rule):
    """Detect risky operations inside a chroot on remote systems."""

    id = "remote-chroot-guard"
    description = "Blocks bootloader removal in chroot; warns on risky repair commands in chroot"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        rule_config = context.config.get(self.id, {})
        allowed_ops: list[str] = rule_config.get("allowed_ops", [])

        for pattern, label, sev in _CHROOT_PATTERNS:
            if label in allowed_ops:
                continue
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Risky chroot operation detected: {label}",
                        severity=sev,
                        suggestion=(
                            "Running package operations inside a chroot on a broken remote system "
                            "can cascade failures and make recovery harder. Review carefully. "
                            "Add to remote-chroot-guard.allowed_ops in agentlint.yml to permanently allow."
                        ),
                    )
                ]

        return []
