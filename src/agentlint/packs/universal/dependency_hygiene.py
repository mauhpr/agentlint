"""Rule: warn on ad-hoc dependency installation commands."""

from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.utils.shell import split_operations

_BASH_TOOLS = {"Bash"}

# pip install <something> — but not `pip install -e .` (local dev) or `pip install -r` (lockfile).
_PIP_INSTALL_RE = re.compile(r"\bpip3?\s+install\b", re.IGNORECASE)
_PIP_LOCAL_DEV_RE = re.compile(r"\bpip3?\s+install\s+-e\s+\.", re.IGNORECASE)
_PIP_REQUIREMENTS_RE = re.compile(r"(?:^|\s)(?:-r\s*\S+|--requirement(?:\s+|=)\S+)", re.IGNORECASE)

# npm install <package> — but allow bare `npm install` and `npm ci`.
_NPM_INSTALL_PKG_RE = re.compile(
    r"\bnpm\s+install\s+(?!-)[a-zA-Z@]",
    re.IGNORECASE,
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

        # Strip quoted string arguments to avoid false positives on content
        # like: gh pr create --body "... pip install ..."
        from agentlint.utils.bash import strip_string_args

        operations = split_operations(command)
        candidates = [command] if operations is None else [op.text for op in operations]

        violations: list[Violation] = []
        for index, candidate in enumerate(candidates):
            requirements = None
            if operations is not None:
                words = operations[index].words
                requirements = any(
                    (
                        word in {"-r", "--requirement"}
                        and i + 1 < len(words)
                        and not words[i + 1].startswith("-")
                    )
                    or word.startswith("--requirement=")
                    and len(word) > len("--requirement=")
                    or word.startswith("-r")
                    and len(word) > 2
                    for i, word in enumerate(words)
                )
            violations.extend(self._check_command(strip_string_args(candidate), requirements))
        return violations

    def _check_command(self, stripped: str, requirements: bool | None = None) -> list[Violation]:

        violations: list[Violation] = []

        if (
            _PIP_INSTALL_RE.search(stripped)
            and not _PIP_LOCAL_DEV_RE.search(stripped)
            and not (
                requirements if requirements is not None else _PIP_REQUIREMENTS_RE.search(stripped)
            )
        ):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Ad-hoc pip install detected",
                    severity=self.severity,
                    suggestion="Use poetry/uv add to keep dependencies in a lockfile. If installing a global dev tool (e.g., ruff, pre-commit), this warning can be ignored.",
                )
            )

        if _NPM_INSTALL_PKG_RE.search(stripped):
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="Ad-hoc npm install <package> detected",
                    severity=self.severity,
                    suggestion="Use npm ci for reproducible installs.",
                )
            )

        return violations
