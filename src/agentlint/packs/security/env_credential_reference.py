"""Rule: warn when credential file paths are embedded in environment variables."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_ALL_TOOLS = {"Write", "Edit", "MultiEdit", "Bash"}

# Patterns detecting credential-adjacent file paths in env var assignments.
_CRED_FILE_ENV_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # e.g. EZ_PROXIES_LIST_FILE=config/proxies/file.txt in --set-env-vars.
    (re.compile(r'(?:PROXY|CREDENTIAL|SECRET|PASSWORD|TOKEN|KEY|CERT|AUTH)\w*FILE\s*=\s*(?!Secret:)(?!secretmanager:)\S+', re.I),
     "credential-adjacent *_FILE env var"),
    # Env var pointing to config/ or secrets/ directories.
    (re.compile(r'\w+FILE\s*=\s*(?:config|secrets?|creds?|credentials?)/\S+', re.I),
     "env var referencing config/secrets path"),
    # Cloud Run --set-env-vars with *_FILE vars (not referencing Secret Manager).
    (re.compile(r'--set-env-vars\b[^=,]*\w+_FILE\s*=\s*(?!Secret:)(?!secretmanager:)\S+', re.I),
     "Cloud Run --set-env-vars with *_FILE reference"),
]


class EnvCredentialReference(Rule):
    """Warn when credential file paths are embedded in environment variables."""

    id = "env-credential-reference"
    description = "Warns when *_FILE env vars reference local paths (credential leakage risk)"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "security"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _ALL_TOOLS:
            return []

        # Check command for Bash, or file content for file tools.
        if context.tool_name == "Bash":
            content: str = context.command or ""
        else:
            # For Write/Edit, check the new_string or content being written.
            content = (
                context.tool_input.get("new_string")
                or context.tool_input.get("content")
                or ""
            )

        if not content:
            return []

        for pattern, label in _CRED_FILE_ENV_PATTERNS:
            if pattern.search(content):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Credential file path referenced in environment variable: {label}",
                        severity=self.severity,
                        suggestion=(
                            "Verify the referenced file is in .gitignore and not embedded in the container image. "
                            "Prefer GCP Secret Manager / AWS Secrets Manager / GitHub Actions secrets for credential files."
                        ),
                    )
                ]

        return []
