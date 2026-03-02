"""Rule: block cloud infrastructure mutation commands (wide blast radius)."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Each tuple: (compiled_regex, label).
_CLOUD_MUTATION_OPS: list[tuple[re.Pattern[str], str]] = [
    # GCP network/infra mutations
    (re.compile(r"\bgcloud\s+compute\s+routers?\s+nats?\s+(?:update|create)\b", re.I), "GCP Cloud NAT update"),
    (re.compile(r"\bgcloud\s+compute\s+firewall-rules?\s+(?:create|update|delete)\b", re.I), "GCP firewall rule change"),
    (re.compile(r"\bgcloud\s+compute\s+backend-services?\s+(?:update|create)\b", re.I), "GCP backend service change"),
    (re.compile(r"\bgcloud\s+compute\s+forwarding-rules?\s+(?:create|update|delete)\b", re.I), "GCP forwarding rule change"),
    (re.compile(r"\bgcloud\s+compute\s+networks?\s+(?:create|delete|update)\b", re.I), "GCP VPC network change"),
    (re.compile(r"\bgcloud\s+projects?\s+add-iam-policy-binding\b", re.I), "GCP IAM policy binding"),
    # AWS network/infra mutations
    (re.compile(r"\baws\s+ec2\s+(?:authorize|revoke)-security-group-(?:ingress|egress)\b", re.I), "AWS security group rule change"),
    (re.compile(r"\baws\s+ec2\s+modify-(?:vpc|subnet|route-table|internet-gateway)\b", re.I), "AWS VPC mutation"),
    (re.compile(r"\baws\s+iam\s+(?:attach|detach|put)-(?:user|role|group)-policy\b", re.I), "AWS IAM policy change"),
    (re.compile(r"\baws\s+ec2\s+(?:create|delete)-route\b", re.I), "AWS route table change"),
    (re.compile(r"\baws\s+elbv2\s+(?:create|modify|delete)-(?:listener|rule|target-group)\b", re.I), "AWS load balancer change"),
    # Azure
    (re.compile(r"\baz\s+network\s+nsg\s+rule\s+(?:create|update|delete)\b", re.I), "Azure NSG rule change"),
    (re.compile(r"\baz\s+network\s+(?:vnet|subnet)\s+(?:create|update|delete)\b", re.I), "Azure VNet change"),
    (re.compile(r"\baz\s+role\s+assignment\s+create\b", re.I), "Azure role assignment"),
]


class CloudInfraMutation(Rule):
    """Block cloud infrastructure mutations that have wide blast radius."""

    id = "cloud-infra-mutation"
    description = "Blocks NAT, firewall, VPC, IAM, and load balancer mutations across AWS/GCP/Azure"
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

        for pattern, label in _CLOUD_MUTATION_OPS:
            if label in allowed_ops:
                continue
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Cloud infrastructure mutation with wide blast radius: {label}",
                        severity=self.severity,
                        suggestion=(
                            "Review the blast radius before running this command — it may affect all users "
                            "of shared infrastructure. Approve manually or add to "
                            "cloud-infra-mutation.allowed_ops in agentlint.yml."
                        ),
                    )
                ]

        return []
