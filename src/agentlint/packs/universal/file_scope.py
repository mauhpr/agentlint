"""Rule: restrict file access based on allow/deny glob patterns.

Blocks Write, Edit, and Read operations on files outside the allowed scope.
Deny patterns take precedence over allow patterns. If no file-scope config
is present, the rule is inactive (zero-config = no restrictions).
"""
from __future__ import annotations

import logging
import os
import re
from fnmatch import fnmatch

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

logger = logging.getLogger("agentlint")

_FILE_TOOLS = {"Write", "Edit", "Read"}

# Patterns to extract file paths from Bash commands
_BASH_FILE_PATTERNS = [
    re.compile(r"\b(?:cat|head|tail|less|more)\s+(?:\"([^\"]+)\"|'([^']+)'|(\S+))"),
    re.compile(r"\b(?:rm|cp|mv)\s+(?:-\S+\s+)*(?:\"([^\"]+)\"|'([^']+)'|(\S+))"),
]


class FileScope(Rule):
    id = "file-scope"
    description = "Restricts file access based on allow/deny glob patterns"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        rule_config = context.config.get(self.id, {})
        allow = rule_config.get("allow", [])
        deny = rule_config.get("deny", [])

        if not allow and not deny:
            return []  # No config = inactive

        paths = self._extract_paths(context)
        if not paths:
            return []

        violations: list[Violation] = []
        deny_message = rule_config.get("deny_message", "File access denied by file-scope rule")

        for file_path in paths:
            if not self._is_allowed(file_path, allow, deny, context.project_dir):
                violations.append(Violation(
                    rule_id=self.id,
                    message=f"{deny_message}: {file_path}",
                    severity=self.severity,
                    file_path=file_path,
                    suggestion="Check file-scope allow/deny patterns in agentlint.yml",
                ))

        return violations

    def _extract_paths(self, context: RuleContext) -> list[str]:
        """Extract file paths from the tool call."""
        paths: list[str] = []

        if context.tool_name in _FILE_TOOLS:
            fp = context.file_path
            if fp:
                paths.append(fp)
        elif context.tool_name == "Bash":
            command = context.command or ""
            for pattern in _BASH_FILE_PATTERNS:
                for match in pattern.finditer(command):
                    # Groups: quoted double, quoted single, unquoted
                    path = match.group(1) or match.group(2) or match.group(3)
                    if path and not path.startswith("-"):
                        paths.append(path)

        return paths

    def _is_allowed(
        self, file_path: str, allow: list[str], deny: list[str], project_dir: str,
    ) -> bool:
        """Check if a file path is allowed. Deny takes precedence."""
        resolved = os.path.realpath(file_path)
        project_real = os.path.realpath(project_dir)

        # Compute relative path for glob matching
        try:
            relative = os.path.relpath(resolved, project_real)
        except ValueError:
            relative = resolved

        # All candidate paths to match against (handles macOS symlinks like /etc → /private/etc)
        candidates = {relative, resolved, file_path, os.path.basename(resolved)}

        # Deny takes precedence
        for pattern in deny:
            if any(fnmatch(c, pattern) for c in candidates):
                return False

        # If allow list is empty, everything not denied is allowed
        if not allow:
            return True

        # If allow list exists, file must match at least one pattern
        for pattern in allow:
            if any(fnmatch(c, pattern) for c in candidates):
                return True

        return False
