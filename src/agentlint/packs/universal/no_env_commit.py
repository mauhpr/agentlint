"""Rule: block writing to .env files that may contain secrets."""
from __future__ import annotations

import os
import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}
_BASH_TOOLS = {"Bash"}

# Patterns that are safe templates and should be allowed.
_SAFE_SUFFIXES = (".example", ".template", ".sample")

# .env filenames that should be blocked.
_BLOCKED_RE = re.compile(
    r"(^|/)\.env(\.local|\.production|\.staging|\.development)?$"
)

# Patterns that extract file paths from Bash commands targeting .env files.
# Matches: cat > .env, echo ... > .env, tee .env, cp ... .env, sed -i ... .env,
#          heredocs writing to .env, printf ... > .env
_BASH_ENV_TARGET_RE = re.compile(
    r"""(?:"""
    r""">+\s*|tee\s+(?:-a\s+)?|cp\s+\S+\s+|mv\s+\S+\s+|sed\s+.*?\s+"""
    r""")"""
    r"""((?:\S*/)?\.env(?:\.local|\.production|\.staging|\.development)?)"""
    r"""(?:\s|$|;|&&|\|)""",
)


def _is_safe_env_path(path: str) -> bool:
    """Return True if path is a safe template file."""
    basename = os.path.basename(path)
    return any(basename.endswith(suffix) for suffix in _SAFE_SUFFIXES)


class NoEnvCommit(Rule):
    """Block writing to .env files that may contain real secrets."""

    id = "no-env-commit"
    description = "Prevents writing to .env files that may contain secrets"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        # Handle Write/Edit tools.
        if context.tool_name in _WRITE_TOOLS:
            return self._check_file_path(context.file_path)

        # Handle Bash tool.
        if context.tool_name in _BASH_TOOLS:
            return self._check_bash_command(context.command or "")

        return []

    def _check_file_path(self, file_path: str | None) -> list[Violation]:
        """Check if a Write/Edit file path targets a .env file."""
        if not file_path:
            return []

        if _is_safe_env_path(file_path):
            return []

        if _BLOCKED_RE.search(file_path):
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Writing to env file is blocked: {file_path}",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Use .env.example for templates; keep real .env out of version control.",
                )
            ]

        return []

    def _check_bash_command(self, command: str) -> list[Violation]:
        """Scan a Bash command for file paths targeting .env files."""
        if not command:
            return []

        violations: list[Violation] = []
        seen: set[str] = set()

        for match in _BASH_ENV_TARGET_RE.finditer(command):
            env_path = match.group(1)
            if env_path in seen:
                continue
            seen.add(env_path)
            if not _is_safe_env_path(env_path):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Bash command writes to env file: {env_path}",
                        severity=self.severity,
                        file_path=env_path,
                        suggestion="Use .env.example for templates; keep real .env out of version control.",
                    )
                )

        return violations
