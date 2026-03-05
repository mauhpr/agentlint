"""Rule: block deletion or overwrite of boot-critical files on remote systems."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Match paths like /boot/..., /mnt/boot/..., /target/boot/...
_BOOT_RM_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\b.*(?:/(?:mnt|target))?/boot/vmlinuz", re.I), "rm boot/vmlinuz (kernel image)"),
    (re.compile(r"\brm\b.*(?:/(?:mnt|target))?/boot/initrd", re.I), "rm boot/initrd (initial ramdisk)"),
    (re.compile(r"\brm\b.*(?:/(?:mnt|target))?/boot/grub/", re.I), "rm boot/grub (bootloader config)"),
    (re.compile(r"\bdd\b.*\bof=.*(?:/(?:mnt|target))?/boot\b", re.I), "dd of= targeting boot partition"),
]


class RemoteBootPartitionGuard(Rule):
    """Block deletion or overwrite of boot-critical files."""

    id = "remote-boot-partition-guard"
    description = "Blocks rm or dd targeting boot-critical paths (/boot/vmlinuz, /boot/initrd, /boot/grub)"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        for pattern, label in _BOOT_RM_PATTERNS:
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Boot-critical file operation detected: {label}",
                        severity=self.severity,
                        suggestion=(
                            "Deleting or overwriting boot-critical files can render the system "
                            "unbootable. This is especially dangerous on remote servers where "
                            "physical access is not possible. Do NOT proceed without human approval."
                        ),
                    )
                ]

        return []
