"""Rule: block Bash commands targeting production environments."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Patterns that indicate a production environment target.
# Each tuple: (compiled_regex, human-readable label).
_PROD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # PostgreSQL connection strings with prod/production/live in host.
    (re.compile(
        r"\bpsql\b.*postgresql://[^@]+@[^/]*(?:prod(?:uction)?|live)[^/]*/",
        re.IGNORECASE,
    ), "psql → production connection string"),
    # psql -h <prod-host> (host contains prod/production/live followed by - or .)
    (re.compile(
        r"\bpsql\b.*-h\s+\S*(?:prod(?:uction)?|live)[-.]",
        re.IGNORECASE,
    ), "psql → production host"),
    # psql -d production (database name is exactly prod/production/live)
    (re.compile(
        r"\bpsql\b.*-d\s+(?:prod(?:uction)?|live)\b",
        re.IGNORECASE,
    ), "psql → production database name"),
    # mysql with prod host
    (re.compile(
        r"\bmysql\b.*-h\s+\S*(?:prod(?:uction)?|live)\S*",
        re.IGNORECASE,
    ), "mysql → production host"),
    # gcloud --project=<prod-named-project>
    (re.compile(
        r"\bgcloud\b.*--project[=\s]+\S*(?:prod(?:uction)?|live)\S*",
        re.IGNORECASE,
    ), "gcloud → production project"),
    # aws --profile prod*
    (re.compile(
        r"\baws\b.*--profile\s+(?:prod(?:uction)?|live)\S*",
        re.IGNORECASE,
    ), "aws → production profile"),
    # AWS_PROFILE=prod* environment variable
    (re.compile(
        r"\bAWS_PROFILE\s*=\s*(?:prod(?:uction)?|live)\S*",
        re.IGNORECASE,
    ), "AWS_PROFILE → production"),
]

# Extract project/host identifiers for allowlist checking.
_PROJECT_RE = re.compile(r"--project[=\s]+(\S+)", re.IGNORECASE)
_HOST_RE = re.compile(r"(?:-h\s+(\S+)|@([^/:]+))", re.IGNORECASE)


def _extract_project(command: str) -> str | None:
    m = _PROJECT_RE.search(command)
    return m.group(1).strip("'\"") if m else None


def _extract_host(command: str) -> str | None:
    m = _HOST_RE.search(command)
    if m:
        return (m.group(1) or m.group(2) or "").strip("'\"") or None
    return None


class ProductionGuard(Rule):
    """Block Bash commands that target production databases, cloud projects, or accounts."""

    id = "production-guard"
    description = "Blocks commands targeting production environments (DB, gcloud, AWS)"
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
        allowed_projects: list[str] = [p.lower() for p in rule_config.get("allowed_projects", [])]
        allowed_hosts: list[str] = [h.lower() for h in rule_config.get("allowed_hosts", [])]

        # Check allowlists before pattern matching.
        project = _extract_project(command)
        if project and project.lower() in allowed_projects:
            return []

        host = _extract_host(command)
        if host and host.lower() in allowed_hosts:
            return []

        for pattern, label in _PROD_PATTERNS:
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Production environment detected: {label}",
                        severity=self.severity,
                        suggestion=(
                            "Add this project/host to production-guard.allowed_projects or "
                            "allowed_hosts in agentlint.yml if this is intentional."
                        ),
                    )
                ]

        return []
