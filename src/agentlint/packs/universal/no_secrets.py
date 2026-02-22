"""Rule: block secrets and credentials from being written to files."""
from __future__ import annotations

import os
import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}
_BASH_TOOLS = {"Bash"}

# Literal token prefixes that indicate a real secret.
_TOKEN_PREFIXES = (
    "sk_live_", "sk_test_", "AKIA",
    "ghp_", "ghs_", "gho_", "github_pat_",
    "xoxb-", "xoxp-", "xoxs-",
    "_authToken",
)

# Pattern matching key=value assignments for secret-like keys.
_KEY_VALUE_RE = re.compile(
    r"""(api_key|apikey|secret|password|token|secret_key|private_key|auth_token)"""
    r"""\s*=\s*["']([^"']{10,})["']""",
    re.IGNORECASE,
)

# Bearer tokens.
_BEARER_RE = re.compile(r"Bearer [a-zA-Z0-9\-_.]{20,}")

# Private key blocks.
_PRIVATE_KEY_RE = re.compile(r"-----BEGIN\s+(?:\w+\s+)?PRIVATE KEY-----")

# Google Cloud service account JSON.
_GCP_SERVICE_ACCOUNT_RE = re.compile(r'"type"\s*:\s*"service_account"')

# Database connection strings with embedded credentials.
# Use a greedy match for the password up to the last @ before the host.
_DB_CONN_RE = re.compile(
    r"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://"
    r"[^:]+:(.+)@(?!localhost\b)(?!127\.0\.0\.1\b)(?!db\b)\S+",
    re.IGNORECASE,
)

# JWT tokens: three base64url segments separated by dots.
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")

# Curl with embedded credentials.
_CURL_AUTH_RE = re.compile(
    r"\bcurl\b.*(?:-u\s+\S+:\S+|-H\s+[\"']Authorization:\s+(?:Bearer|Basic)\s+\S+[\"'])",
    re.IGNORECASE,
)

# Terraform state files.
_TERRAFORM_STATE_RE = re.compile(r'"serial"\s*:\s*\d+.*"lineage"', re.DOTALL)

# Values that are obviously placeholders and should be ignored.
_PLACEHOLDER_WORDS = {"test", "example", "placeholder", "xxx", "changeme", "password", "secret"}

# DB password placeholders.
_DB_PLACEHOLDER_PASSWORDS = {"password", "pass", "secret", "changeme", "example", "placeholder"}

# Env-var reference patterns — safe to keep in source.
_ENV_REF_PATTERNS = ("os.environ", "process.env", "${")

# Filenames that should never be written as-is.
_SENSITIVE_FILENAMES = ("credentials", "secrets")


def _is_placeholder(value: str) -> bool:
    """Return True if *value* looks like a harmless placeholder."""
    lower = value.strip().lower()
    return lower in _PLACEHOLDER_WORDS


def _has_env_ref(value: str) -> bool:
    """Return True if *value* references an environment variable."""
    return any(ref in value for ref in _ENV_REF_PATTERNS)


def _is_db_placeholder(password: str) -> bool:
    """Return True if a DB connection password is a placeholder."""
    return password.lower() in _DB_PLACEHOLDER_PASSWORDS


class NoSecrets(Rule):
    """Block secrets and credentials from being written to files."""

    id = "no-secrets"
    description = "Prevents writing secrets or credentials into source files"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS and context.tool_name not in _BASH_TOOLS:
            return []

        violations: list[Violation] = []

        # Extract content to scan: file content for Write/Edit, command for Bash.
        if context.tool_name in _BASH_TOOLS:
            content = context.command or ""
            file_path = None
        else:
            content = context.tool_input.get("content", "")
            file_path = context.file_path

        # Load config for extra prefixes.
        rule_config = context.config.get(self.id, {})
        extra_prefixes: list[str] = rule_config.get("extra_prefixes", [])

        # Check for sensitive filenames (only for Write/Edit).
        if file_path and context.tool_name in _WRITE_TOOLS:
            basename = os.path.basename(file_path).lower()
            for name in _SENSITIVE_FILENAMES:
                if name in basename:
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=f"Writing to a file with sensitive name: {file_path}",
                            severity=self.severity,
                            file_path=file_path,
                            suggestion="Avoid committing files named 'credentials' or 'secrets'.",
                        )
                    )

        if not content:
            return violations

        # Check literal token prefixes.
        all_prefixes = list(_TOKEN_PREFIXES) + extra_prefixes
        for prefix in all_prefixes:
            if prefix in content:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Possible secret token detected (prefix '{prefix}')",
                        severity=self.severity,
                        file_path=file_path,
                        suggestion="Use environment variables instead of hard-coded secrets.",
                    )
                )

        # Check key=value secret assignments.
        for match in _KEY_VALUE_RE.finditer(content):
            value = match.group(2)
            if _is_placeholder(value) or _has_env_ref(value):
                continue
            violations.append(
                Violation(
                    rule_id=self.id,
                    message=f"Secret assignment detected: {match.group(1)}=...",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Use environment variables instead of hard-coded secrets.",
                )
            )

        # Check Bearer tokens.
        for match in _BEARER_RE.finditer(content):
            if _has_env_ref(match.group()):
                continue
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Bearer token detected in content",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Use environment variables instead of hard-coded Bearer tokens.",
                )
            )

        # Private key blocks.
        if _PRIVATE_KEY_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Private key detected in content",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Never commit private keys. Use a secrets manager or environment variables.",
                )
            )

        # GCP service account JSON.
        if _GCP_SERVICE_ACCOUNT_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Google Cloud service account key detected",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Use workload identity or environment variables instead of service account keys.",
                )
            )

        # Database connection strings with real passwords.
        for match in _DB_CONN_RE.finditer(content):
            password = match.group(1)
            if not _is_db_placeholder(password):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="Database connection string with embedded credentials detected",
                        severity=self.severity,
                        file_path=file_path,
                        suggestion="Use environment variables for database connection strings.",
                    )
                )

        # JWT tokens.
        if _JWT_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="JWT token detected in content",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Never hard-code JWT tokens. Use environment variables or a token service.",
                )
            )

        # Curl with embedded credentials (Bash only).
        if context.tool_name in _BASH_TOOLS and _CURL_AUTH_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Curl command with embedded credentials detected",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Use environment variables or a credentials file instead of inline credentials.",
                )
            )

        # Terraform state detection.
        if _TERRAFORM_STATE_RE.search(content):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Terraform state file detected (may contain secrets)",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Use remote state storage (S3, GCS) instead of committing terraform.tfstate.",
                )
            )

        return violations
