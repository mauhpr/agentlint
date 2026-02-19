"""Rule: warn on ad-hoc dependency installation commands."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# pip install <something> — but not `pip install -e .` (local dev) or `pip install -r` (lockfile).
_PIP_INSTALL_RE = re.compile(r"\bpip3?\s+install\b", re.IGNORECASE)
_PIP_LOCAL_DEV_RE = re.compile(r"\bpip3?\s+install\s+-e\s+\.", re.IGNORECASE)
_PIP_REQUIREMENTS_RE = re.compile(r"\bpip3?\s+install\s+-r\s+", re.IGNORECASE)

# npm install <package> — but allow bare `npm install` and `npm ci`.
_NPM_INSTALL_PKG_RE = re.compile(
    r"\bnpm\s+install\s+(?!-)[a-zA-Z@]", re.IGNORECASE,
)


class DependencyHygiene(Rule):
    """Warn on ad-hoc dependency installation; prefer lockfile-based tools."""

    id = "dependency-hygiene"
    description = "Suggests using lockfile-based tools instead of ad-hoc pip/npm install"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        violations: list[Violation] = []

        if _PIP_INSTALL_RE.search(command) and not _PIP_LOCAL_DEV_RE.search(command) and not _PIP_REQUIREMENTS_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Ad-hoc pip install detected",
                    severity=self.severity,
                    suggestion="Use poetry/uv add to keep dependencies in a lockfile.",
                )
            )

        if _NPM_INSTALL_PKG_RE.search(command):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Ad-hoc npm install <package> detected",
                    severity=self.severity,
                    suggestion="Use npm ci for reproducible installs.",
                )
            )

        return violations
