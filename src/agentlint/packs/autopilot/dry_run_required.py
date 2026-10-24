"""Rule: require --dry-run/--check/plan flags for infrastructure apply commands."""

from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.utils.shell import executable_operations, executable_words

_BASH_TOOLS = {"Bash"}

# Each entry: (apply_pattern, safe_pattern, label)
# NOTE: safe patterns for -- flags must NOT use \b because '-' is a non-word character
# and \b never matches at the boundary between two non-word characters (space + dash).
_INFRA_RULES: list[tuple[re.Pattern[str], re.Pattern[str], str]] = [
    (
        re.compile(r"\bterraform\s+apply\b", re.IGNORECASE),
        re.compile(r"\bterraform\s+plan\b|--dry-run", re.IGNORECASE),
        "terraform apply",
    ),
    (
        re.compile(r"\bansible-playbook\b", re.IGNORECASE),
        re.compile(r"--check", re.IGNORECASE),
        "ansible-playbook",
    ),
    (
        re.compile(r"\bkubectl\s+apply\b", re.IGNORECASE),
        re.compile(r"--dry-run", re.IGNORECASE),
        "kubectl apply",
    ),
    (
        re.compile(r"\bhelm\s+(?:upgrade|install)\b", re.IGNORECASE),
        re.compile(r"--dry-run", re.IGNORECASE),
        "helm upgrade/install",
    ),
    (
        re.compile(r"\bpulumi\s+up\b", re.IGNORECASE),
        re.compile(r"--dry-run|\bpulumi\s+preview\b", re.IGNORECASE),
        "pulumi up",
    ),
]


class DryRunRequired(Rule):
    """Require --dry-run/--check flags for infrastructure apply commands."""

    id = "dry-run-required"
    description = "Requires --dry-run/--check for terraform, kubectl, ansible, helm before apply"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        operations = executable_operations(
            command, {"terraform", "ansible-playbook", "kubectl", "helm", "pulumi"}
        )

        rule_config = context.config.get(self.id, {})
        bypass_tools: list[str] = rule_config.get("bypass_tools", [])

        violations: list[Violation] = []
        if operations is not None:
            previews = set()
            for operation in operations:
                words = executable_words(list(operation.words)) or []
                if not words:
                    continue
                binary, args = words[0].rsplit("/", 1)[-1], words[1:]
                canonical = " ".join([binary, *args])
                if (binary, tuple(args[:1])) in {
                    ("terraform", ("plan",)),
                    ("pulumi", ("preview",)),
                }:
                    previews.add(binary)
                for apply_re, _, label in _INFRA_RULES:
                    match = apply_re.match(canonical)
                    safe_flag = any(
                        arg == "--dry-run" or arg.startswith("--dry-run=") for arg in args
                    )
                    if binary == "ansible-playbook":
                        safe_flag = "--check" in args
                    if (
                        match
                        and label not in bypass_tools
                        and not safe_flag
                        and binary not in previews
                    ):
                        violations.append(self._violation(label, match.group(0)))
            return violations

        for apply_re, safe_re, label in _INFRA_RULES:
            if label in bypass_tools:
                continue
            if apply_re.search(command) and not safe_re.search(command):
                violations.append(self._violation(label, label))
        return violations

    def _violation(self, label: str, matched: str) -> Violation:
        return Violation(
            rule_id=self.id,
            message=f"Infrastructure apply without preview: {label}",
            severity=self.severity,
            operation=matched,
            suggestion=(
                "Run the preview form first (e.g. terraform plan, kubectl apply --dry-run=client). "
                "Add to dry-run-required.bypass_tools in agentlint.yml to allow."
            ),
        )
