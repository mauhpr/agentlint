"""Rule: block secrets and credentials from being written to files."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import replace
from fnmatch import fnmatch

from agentlint.config import get_rule_setting
from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}
_BASH_TOOLS = {"Bash"}

# Secrets manager CLI invocations — anchored to command start.
_SECRETS_MANAGER_START_RE = re.compile(
    r"^(?:export\s+\w+=)?\$?\(?\s*(?:gcloud\s+secrets\s+versions\s+access"
    r"|aws\s+secretsmanager\s+get-secret-value"
    r"|az\s+keyvault\s+secret\s+show"
    r"|vault\s+kv\s+get"
    r"|op\s+(?:item\s+get|read)"
    r"|doppler\s+secrets\s+get"
    r"|chamber\s+read)\b",
    re.IGNORECASE,
)

# Safe text-processing tools allowed in a secrets pipeline.
_SAFE_PIPE_TOOLS = re.compile(
    r"^\s*(?:sed|awk|grep|cut|tr|head|tail|jq|sort|uniq|wc|xargs\s+\w+)\b"
)


def _is_secrets_manager_pipeline(command: str) -> bool:
    """True if command is a secrets-manager read piped through safe text tools."""
    # Chained commands (&&, ||) are not trusted.
    if re.search(r"\s*(?:&&|\|\|)\s*", command):
        return False
    # Split on pipes.
    parts = command.split("|")
    if not parts or not _SECRETS_MANAGER_START_RE.search(parts[0]):
        return False
    # All subsequent pipe stages must be safe text-processing tools.
    return all(_SAFE_PIPE_TOOLS.match(p) for p in parts[1:])


# Literal token prefixes that indicate a real secret.
_TOKEN_PREFIXES = (
    "sk_live_",
    "sk_test_",
    "AKIA",
    "ghp_",
    "ghs_",
    "gho_",
    "github_pat_",
    "xoxb-",
    "xoxp-",
    "xoxs-",
)

# Pattern matching key=value assignments for secret-like keys.
_KEY_VALUE_RE = re.compile(
    r"""\b([A-Za-z_][A-Za-z_0-9]*)"""
    r"""\s*=\s*["']([^"']{10,})["']""",
    re.IGNORECASE,
)
_SECRET_KEY_RE = re.compile(
    r"(?:api_?key|secret|password|token|secret_?key|private_?key|auth_?token)$",
    re.IGNORECASE,
)
_SYMBOLIC_TOKEN_RE = re.compile(r"[A-Z][a-z]+(?:[A-Z][a-z]+)+")
_NPM_AUTH_RE = re.compile(r"\b_authToken\s*=\s*['\"]?([A-Za-z0-9_-]{10,})")

# Bearer tokens.
_BEARER_RE = re.compile(r"Bearer [a-zA-Z0-9\-_.]{20,}")

# Private key blocks.
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN\s+(?:\w+\s+)?PRIVATE KEY-----[\s\S]*?"
    r"(?:-----END\s+(?:\w+\s+)?PRIVATE KEY-----|$)"
)

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
        findings = self._scan(context)
        before = context.file_content_before
        if context.tool_name != "Edit" or before is None:
            return findings
        previous = self._scan(
            replace(
                context,
                tool_input={**context.tool_input, "content": before},
                file_content=before,
            )
        )
        existing = Counter(item.finding_id for item in previous)
        introduced = []
        for item in findings:
            if existing[item.finding_id]:
                existing[item.finding_id] -= 1
            else:
                introduced.append(item)
        return introduced

    def _scan(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS and context.tool_name not in _BASH_TOOLS:
            return []

        violations: list[Violation] = []

        # Extract content to scan: file content for Write/Edit, command for Bash.
        if context.tool_name in _BASH_TOOLS:
            content = context.command or ""
            file_path = None
        else:
            content = context.file_content
            if content is None:
                content = context.tool_input.get(
                    "content", context.tool_input.get("new_string", "")
                )
            file_path = context.file_path

        def report(message: str, evidence: str, offset: int, suggestion: str) -> None:
            identity = hashlib.sha256((self.id + "\0" + evidence).encode()).hexdigest()
            violations.append(
                Violation(
                    rule_id=self.id,
                    message=message,
                    severity=self.severity,
                    file_path=file_path,
                    line=content.count("\n", 0, offset) + 1,
                    finding_id=identity,
                    suggestion=suggestion,
                )
            )

        # Load config for extra prefixes and allow_paths.
        extra_prefixes: list[str] = get_rule_setting(context.config, self.id, "extra_prefixes", [])
        strict_mode: bool = get_rule_setting(context.config, self.id, "strict_mode", False)
        allow_paths: list[str] = get_rule_setting(context.config, self.id, "allow_paths", [])

        # Skip files matching allow_paths (e.g. test files with mock tokens).
        if file_path and allow_paths and any(fnmatch(file_path, p) for p in allow_paths):
            return []

        # Check for sensitive filenames (only for Write/Edit).
        if file_path and context.tool_name in _WRITE_TOOLS:
            basename = os.path.basename(file_path).lower()
            stem, suffix = os.path.splitext(basename)
            for name in _SENSITIVE_FILENAMES:
                if stem == name or (
                    suffix
                    in {
                        ".json",
                        ".yaml",
                        ".yml",
                        ".toml",
                        ".ini",
                        ".cfg",
                        ".conf",
                        ".env",
                        ".txt",
                        ".xml",
                        ".csv",
                    }
                    and re.search(rf"(?:^|[._-]){name}(?:[._-]|$)", basename)
                ):
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=f"Writing to a file with sensitive name: {file_path}",
                            severity=self.severity,
                            finding_id=hashlib.sha256(
                                ("filename:" + basename).encode()
                            ).hexdigest(),
                            file_path=file_path,
                            suggestion="Avoid committing files named 'credentials' or 'secrets'.",
                        )
                    )

        if not content:
            return violations

        # Check literal token prefixes.
        all_prefixes = list(_TOKEN_PREFIXES) + extra_prefixes
        for prefix in all_prefixes:
            for match in re.finditer(re.escape(prefix) + r"[A-Za-z0-9_-]+", content):
                report(
                    f"Possible secret token detected (prefix '{prefix}')",
                    match.group(),
                    match.start(),
                    "Use environment variables instead of hard-coded secrets.",
                )

        # Check key=value secret assignments.
        for match in _KEY_VALUE_RE.finditer(content):
            value = match.group(2)
            key = match.group(1)
            if not _SECRET_KEY_RE.search(key):
                continue
            # Constant lexical tokens can name public symbols, such as XBRL axes.
            # Known credential prefixes remain independently checked above.
            symbolic = (
                key.isupper()
                and key.lower().endswith("token")
                and _SYMBOLIC_TOKEN_RE.fullmatch(value)
            )
            if symbolic or _is_placeholder(value) or _has_env_ref(value):
                continue
            report(
                f"Secret assignment detected: {key}=...",
                key + "\0" + value,
                match.start(),
                "Use environment variables instead of hard-coded secrets.",
            )

        for match in _NPM_AUTH_RE.finditer(content):
            if not _is_placeholder(match.group(1)):
                report(
                    "npm registry credential detected",
                    match.group(1),
                    match.start(),
                    "Use a credential reference instead of a literal npm token.",
                )

        # Check Bearer tokens.
        for match in _BEARER_RE.finditer(content):
            if _has_env_ref(match.group()):
                continue
            report(
                "Bearer token detected in content",
                match.group(),
                match.start(),
                "Use environment variables instead of hard-coded Bearer tokens.",
            )

        # Private key blocks.
        for match in _PRIVATE_KEY_RE.finditer(content):
            report(
                "Private key detected in content",
                match.group(),
                match.start(),
                "Never commit private keys. Use a secrets manager or environment variables.",
            )

        # GCP service account JSON.
        for match in _GCP_SERVICE_ACCOUNT_RE.finditer(content):
            report(
                "Google Cloud service account key detected",
                "service-account-type",
                match.start(),
                "Use workload identity or environment variables instead of service account keys.",
            )

        # Database connection strings with real passwords.
        # Skip for secrets-manager pipelines (e.g. gcloud secrets ... | sed)
        # unless strict_mode is enabled.
        is_secrets_read = (
            context.tool_name in _BASH_TOOLS
            and not strict_mode
            and _is_secrets_manager_pipeline(content)
        )
        if not is_secrets_read:
            for match in _DB_CONN_RE.finditer(content):
                password = match.group(1)
                if not _is_db_placeholder(password):
                    report(
                        "Database connection string with embedded credentials detected",
                        match.group(),
                        match.start(),
                        "Use environment variables for database connection strings.",
                    )

        # JWT tokens.
        for match in _JWT_RE.finditer(content):
            report(
                "JWT token detected in content",
                match.group(),
                match.start(),
                "Never hard-code JWT tokens. Use environment variables or a token service.",
            )

        # Curl with embedded credentials (Bash only).
        if context.tool_name in _BASH_TOOLS and (match := _CURL_AUTH_RE.search(content)):
            report(
                "Curl command with embedded credentials detected",
                match.group(),
                match.start(),
                "Use environment variables or a credentials file instead of inline credentials.",
            )

        # Terraform state detection.
        if match := _TERRAFORM_STATE_RE.search(content):
            try:
                evidence = json.dumps(json.loads(content), sort_keys=True, separators=(",", ":"))
            except (ValueError, RecursionError):
                evidence = match.group()
            report(
                "Terraform state file detected (may contain secrets)",
                evidence,
                match.start(),
                "Use remote state storage (S3, GCS) instead of committing terraform.tfstate.",
            )

        return violations
