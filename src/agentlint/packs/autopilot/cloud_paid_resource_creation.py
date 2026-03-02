"""Rule: warn when creating paid cloud resources that incur ongoing costs."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Each tuple: (compiled_regex, label, cost_hint).
_PAID_RESOURCE_OPS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bgcloud\s+compute\s+addresses\s+create\b", re.I), "GCP static IP address", "~$0.01/hr each"),
    (re.compile(r"\bgcloud\s+compute\s+disks\s+create\b", re.I), "GCP persistent disk", "charged by GB/month"),
    (re.compile(r"\bgcloud\s+compute\s+instances\s+create\b", re.I), "GCP Compute Engine instance", "ongoing VM cost"),
    (re.compile(r"\bgcloud\s+sql\s+instances\s+create\b", re.I), "GCP Cloud SQL instance", "ongoing DB cost"),
    (re.compile(r"\bgcloud\s+container\s+clusters\s+create\b", re.I), "GCP GKE cluster", "ongoing cluster cost"),
    (re.compile(r"\baws\s+ec2\s+allocate-address\b", re.I), "AWS Elastic IP", "~$0.005/hr when idle"),
    (re.compile(r"\baws\s+ec2\s+run-instances\b", re.I), "AWS EC2 instance", "ongoing instance cost"),
    (re.compile(r"\baws\s+rds\s+create-db-instance\b", re.I), "AWS RDS instance", "ongoing DB cost"),
    (re.compile(r"\baws\s+eks\s+create-cluster\b", re.I), "AWS EKS cluster", "ongoing cluster cost"),
    (re.compile(r"\baz\s+vm\s+create\b", re.I), "Azure VM", "ongoing VM cost"),
]


class CloudPaidResourceCreation(Rule):
    """Warn when creating paid cloud resources that incur ongoing costs."""

    id = "cloud-paid-resource-creation"
    description = "Warns when creating paid cloud resources (VMs, IPs, DBs, clusters)"
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
        if rule_config.get("suppress_warnings", False):
            return []

        for pattern, label, cost_hint in _PAID_RESOURCE_OPS:
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Creating paid cloud resource: {label} ({cost_hint})",
                        severity=self.severity,
                        suggestion=(
                            "Confirm this resource creation is intentional — it will incur ongoing costs. "
                            "Set cloud-paid-resource-creation.suppress_warnings: true in agentlint.yml to silence."
                        ),
                    )
                ]

        return []
