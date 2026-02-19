"""Rule: block secrets and credentials from being written to files."""
from __future__ import annotations

import os
import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}
_BASH_TOOLS = {"Bash"}

# Literal token prefixes that indicate a real secret.
_TOKEN_PREFIXES = ("sk_live_", "sk_test_", "AKIA", "ghp_", "ghs_")

# Pattern matching key=value assignments for secret-like keys.
_KEY_VALUE_RE = re.compile(
    r"""(api_key|apikey|secret|password|token|secret_key|private_key)"""
    r"""\s*=\s*["']([^"']{10,})["']""",
    re.IGNORECASE,
)

# Bearer tokens.
_BEARER_RE = re.compile(r"Bearer [a-zA-Z0-9\-_.]{20,}")

# Values that are obviously placeholders and should be ignored.
_PLACEHOLDER_WORDS = {"test", "example", "placeholder", "xxx", "changeme"}

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
        for prefix in _TOKEN_PREFIXES:
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

        return violations
