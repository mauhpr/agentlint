"""Rule: block firewall mutations and routing changes that open network exposure."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Each tuple: (compiled_regex, label).
_FIREWALL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # iptables
    (re.compile(r"\biptables\s+-F\b", re.I), "iptables flush (removes all rules)"),
    (re.compile(r"\biptables\s+-X\b", re.I), "iptables chain deletion"),
    (re.compile(r"\biptables\b.*0\.0\.0\.0/0", re.I), "iptables rule allowing all IPs"),
    # ufw
    (re.compile(r"\bufw\s+disable\b", re.I), "ufw disable (removes firewall)"),
    (re.compile(r"\bufw\s+allow\s+from\s+any\b|\bufw\s+allow\b.*0\.0\.0\.0/0", re.I), "ufw allow from any"),
    # firewalld
    (re.compile(r"\bfirewall-cmd\b.*(?:--add-port|--add-service).*--permanent", re.I), "firewalld permanent rule"),
    (re.compile(r"\bfirewall-cmd\b.*--zone=public.*--add-(?:port|service)", re.I), "firewalld public zone rule"),
    # Route/DNS mutations
    (re.compile(r"\broute\s+add\s+default\b", re.I), "default route change"),
    (re.compile(r"\bip\s+route\s+(?:add|del|change)\s+default", re.I), "default route mutation"),
    (re.compile(r">\s*/etc/resolv\.conf\b", re.I), "DNS resolver overwrite"),
]


class NetworkFirewallGuard(Rule):
    """Block firewall mutations and routing changes that open network exposure."""

    id = "network-firewall-guard"
    description = "Blocks iptables flush, ufw disable, firewalld permanent rules, and default route changes"
    severity = Severity.ERROR
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

        for pattern, label in _FIREWALL_PATTERNS:
            if label in allowed_ops:
                continue
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Network/firewall mutation detected: {label}",
                        severity=self.severity,
                        suggestion=(
                            "This command modifies firewall rules or routing, potentially exposing the system "
                            "to network attacks. Review carefully and run manually after human approval. "
                            "Add to network-firewall-guard.allowed_ops in agentlint.yml to permanently allow."
                        ),
                    )
                ]

        return []
