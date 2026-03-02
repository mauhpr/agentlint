"""Rule: block package publishing commands to prevent supply-chain incidents."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Each tuple: (compiled_regex, label, severity).
_PUBLISH_OPS: list[tuple[re.Pattern[str], str, Severity]] = [
    # npm/yarn/pnpm — ERROR.
    (re.compile(r"\bnpm\s+publish\b", re.I), "npm publish", Severity.ERROR),
    (re.compile(r"\byarn\s+publish\b", re.I), "yarn publish", Severity.ERROR),
    (re.compile(r"\bpnpm\s+publish\b", re.I), "pnpm publish", Severity.ERROR),
    # Python — ERROR.
    (re.compile(r"\btwine\s+upload\b", re.I), "twine upload (PyPI)", Severity.ERROR),
    (re.compile(r"\bpython[23]?\s+-m\s+twine\s+upload\b", re.I), "python -m twine upload", Severity.ERROR),
    (re.compile(r"\bflit\s+publish\b", re.I), "flit publish", Severity.ERROR),
    (re.compile(r"\bpoetry\s+publish\b", re.I), "poetry publish", Severity.ERROR),
    # Ruby — ERROR.
    (re.compile(r"\bgem\s+push\b", re.I), "gem push (RubyGems)", Severity.ERROR),
    # Rust — ERROR.
    (re.compile(r"\bcargo\s+publish\b", re.I), "cargo publish (crates.io)", Severity.ERROR),
    # Go — ERROR.
    (re.compile(r"\bgo\s+(?:mod\s+)?publish\b", re.I), "go publish", Severity.ERROR),
    # Docker — WARNING (more common in CI, lower risk per push).
    (re.compile(r"\bdocker\s+push\b", re.I), "docker push", Severity.WARNING),
]


class PackagePublishGuard(Rule):
    """Block package publishing to prevent supply-chain incidents."""

    id = "package-publish-guard"
    description = "Blocks npm publish, twine upload, gem push, cargo publish, and similar registry pushes"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        rule_config = context.config.get(self.id, {})
        allowed_registries: list[str] = rule_config.get("allowed_registries", [])

        # Check if the command targets an allowed registry.
        if allowed_registries:
            for registry in allowed_registries:
                if registry in command:
                    return []

        for pattern, label, sev in _PUBLISH_OPS:
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Package publish detected: {label}",
                        severity=sev,
                        suggestion=(
                            "Publishing packages to public registries is a supply-chain risk. "
                            "Verify the version, changelog, and that no malicious code was injected. "
                            "Add to package-publish-guard.allowed_registries in agentlint.yml for internal registries."
                        ),
                    )
                ]

        return []
