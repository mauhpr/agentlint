"""Rule: warn on any package manager invocation inside a chroot."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Each tuple: (compiled_regex, label).
_CHROOT_PKG_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Debian/Ubuntu
    (re.compile(r"\bchroot\b.*\bapt(?:-get)?\s+(?:install|update|upgrade|dist-upgrade|autoremove)\b", re.I), "chroot apt install/update/upgrade"),
    (re.compile(r"\bchroot\b.*\bdpkg\s+-i\b", re.I), "chroot dpkg -i"),
    # RHEL/Fedora
    (re.compile(r"\bchroot\b.*\byum\s+(?:install|remove|update)\b", re.I), "chroot yum install/remove/update"),
    (re.compile(r"\bchroot\b.*\bdnf\s+(?:install|remove|update)\b", re.I), "chroot dnf install/remove/update"),
    # Arch
    (re.compile(r"\bchroot\b.*\bpacman\s+-[SRU]", re.I), "chroot pacman -S/-R/-U"),
]


class PackageManagerInChroot(Rule):
    """Warn on any package manager invocation inside a chroot."""

    id = "package-manager-in-chroot"
    description = "Warns on apt, dpkg, yum, dnf, or pacman invocations inside a chroot"
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

        for pattern, label in _CHROOT_PKG_PATTERNS:
            if label in allowed_ops:
                continue
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Package manager in chroot detected: {label}",
                        severity=self.severity,
                        suggestion=(
                            "Running package managers in a chroot on a broken system can cascade "
                            "failures and make things worse. Review carefully before proceeding. "
                            "Add to package-manager-in-chroot.allowed_ops in agentlint.yml to permanently allow."
                        ),
                    )
                ]

        return []
