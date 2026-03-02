"""Rule: block cloud resource deletion commands without session confirmation."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Each tuple: (compiled_regex, label, confirmation_key).
_CLOUD_DELETE_OPS: list[tuple[re.Pattern[str], str, str]] = [
    # AWS
    (re.compile(r"\baws\s+ec2\s+terminate-instances\b", re.I), "AWS EC2 terminate-instances", "aws-ec2-terminate"),
    (re.compile(r"\baws\s+rds\s+delete-db-instance\b", re.I), "AWS RDS delete-db-instance", "aws-rds-delete"),
    (re.compile(r"\baws\s+s3\s+rm\b.*--recursive", re.I), "AWS S3 recursive delete", "aws-s3-rm-recursive"),
    (re.compile(r"\baws\s+dynamodb\s+delete-table\b", re.I), "AWS DynamoDB delete-table", "aws-dynamodb-delete"),
    (re.compile(r"\baws\s+lambda\s+delete-function\b", re.I), "AWS Lambda delete-function", "aws-lambda-delete"),
    (re.compile(r"\baws\s+iam\s+delete-(?:user|role|group|policy)\b", re.I), "AWS IAM delete", "aws-iam-delete"),
    (re.compile(r"\baws\s+cloudformation\s+delete-stack\b", re.I), "AWS CloudFormation delete-stack", "aws-cfn-delete"),
    # GCP
    (re.compile(r"\bgcloud\s+compute\s+instances\s+delete\b", re.I), "GCP compute instance delete", "gcloud-compute-delete"),
    (re.compile(r"\bgcloud\s+sql\s+instances\s+delete\b", re.I), "GCP Cloud SQL delete", "gcloud-sql-delete"),
    (re.compile(r"\bgcloud\s+container\s+clusters\s+delete\b", re.I), "GCP GKE cluster delete", "gcloud-gke-delete"),
    (re.compile(r"\bgcloud\s+storage\s+(?:rm|buckets\s+delete)\b.*(?:--recursive|-r|\*)", re.I), "GCP Storage recursive delete", "gcloud-storage-delete"),
    (re.compile(r"\bgcloud\s+run\s+services\s+delete\b", re.I), "GCP Cloud Run service delete", "gcloud-run-delete"),
    # Azure
    (re.compile(r"\baz\s+vm\s+delete\b", re.I), "Azure VM delete", "az-vm-delete"),
    (re.compile(r"\baz\s+(?:sql|mysql|postgres)\s+(?:server\s+)?delete\b", re.I), "Azure database delete", "az-db-delete"),
    (re.compile(r"\baz\s+group\s+delete\b", re.I), "Azure resource group delete", "az-group-delete"),
    (re.compile(r"\baz\s+storage\s+account\s+delete\b", re.I), "Azure storage account delete", "az-storage-delete"),
    (re.compile(r"\baz\s+keyvault\s+delete\b", re.I), "Azure Key Vault delete", "az-keyvault-delete"),
]


class CloudResourceDeletion(Rule):
    """Block cloud resource deletion without explicit session confirmation."""

    id = "cloud-resource-deletion"
    description = "Blocks AWS/GCP/Azure resource deletion without session confirmation"
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

        confirmed: list[str] = context.session_state.get("confirmed_cloud_deletions", [])
        confirmed_lower = [c.lower() for c in confirmed]

        for pattern, label, key in _CLOUD_DELETE_OPS:
            if key in allowed_ops:
                continue
            if pattern.search(command):
                if key.lower() in confirmed_lower:
                    continue
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Cloud resource deletion requires explicit confirmation: {label}",
                        severity=self.severity,
                        suggestion=(
                            f"Set session_state['confirmed_cloud_deletions'] = ['{key}'] "
                            f"before running this command, or add '{key}' to "
                            f"cloud-resource-deletion.allowed_ops in agentlint.yml."
                        ),
                    )
                ]

        return []
