"""Rule: block install of dependencies on the compromised-packages deny list.

Hybrid rule — first of the new architectural class introduced in Phase 17.
The rule logic is fully open-source (you can read it right here) but the
DATA it consults is a cloud-curated deny list of known-compromised
packages, refreshed every 24 hours from AgentChute's API.

Self-degrading: if AgentChute is not configured, the rule is a
silent no-op. The OSS user gets the existing ``dependency-hygiene``
warning either way; only AgentChute-licensed teams get the deny-list
augmentation.

Sourcing of the deny list:
    The AgentChute team maintains a curated registry of NPM, PyPI, and
    RubyGems packages that have been compromised by recent supply-chain
    attacks (Sha1-Hulud, Checkmarx wave, etc.) — sourced from public
    advisories, the security-research community, and the AgentChute
    incident DB. The list is republished hourly.

Why this is a hybrid rule instead of pure-OSS:
    A static "list of bad packages" hard-coded in OSS would be stale
    within hours of the next supply-chain attack. The deny list MUST
    update faster than monthly OSS releases. Continuous freshness is the
    moat — see Phase 17 of the strategy plan.

Why this is a hybrid rule instead of pure-cloud:
    Static rules at lint time are 10ms. A round-trip API call would add
    50–500ms to every Bash invocation, breaking the ergonomic contract
    of AgentLint OSS. Local cache-with-stale-fallback gives us 10ms hot
    path AND fresh data within 24h of upstream changes.
"""

from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.utils.bash import strip_string_args

_BASH_TOOLS = {"Bash"}

# Match `npm install <pkg>`, `npm i <pkg>`, `yarn add <pkg>`, `pnpm add <pkg>`,
# `pip install <pkg>`, `pip3 install <pkg>`, `gem install <pkg>`, `cargo add <pkg>`,
# capturing the FIRST package name. Skip flags (-r, -e, -u, etc.).
_INSTALL_PATTERNS = [
    # npm/yarn/pnpm
    re.compile(r"\bnpm\s+(?:install|i|add)\s+(?!-)([@\w][\w@/\-\.]*)", re.IGNORECASE),
    re.compile(r"\byarn\s+add\s+(?!-)([@\w][\w@/\-\.]*)", re.IGNORECASE),
    re.compile(r"\bpnpm\s+add\s+(?!-)([@\w][\w@/\-\.]*)", re.IGNORECASE),
    # pip / pip3
    re.compile(r"\bpip3?\s+install\s+(?!-)([\w][\w\-\.]*)", re.IGNORECASE),
    # gem
    re.compile(r"\bgem\s+install\s+(?!-)([\w][\w\-\.]*)", re.IGNORECASE),
    # cargo
    re.compile(r"\bcargo\s+(?:add|install)\s+(?!-)([\w][\w\-\.]*)", re.IGNORECASE),
]


def _extract_packages(command: str) -> list[str]:
    """Return all package names mentioned in install-like commands.
    Returns lowercase strings. Multiple installs in one command (e.g.,
    `npm install foo bar`) yield multiple matches via re-scanning."""
    out: list[str] = []
    for pattern in _INSTALL_PATTERNS:
        for match in pattern.finditer(command):
            pkg = match.group(1).lower()
            # Skip empty captures and obviously-bad matches
            if pkg and pkg not in {".", "..", "-r", "-e"}:
                out.append(pkg)
    return out


class NoCompromisedDependency(Rule):
    """Block install of dependencies on the AgentChute deny list.

    Cloud-augmented: requires AGENTCHUTE_LICENSE_KEY to be set for
    the deny list to be consulted. Without it, this rule is a no-op
    (the existing ``dependency-hygiene`` rule still warns about ad-hoc
    installs separately).
    """

    id = "no-compromised-dependency"
    description = (
        "Blocks install of packages on the AgentChute cloud-curated "
        "compromised-packages deny list. Self-degrades to no-op when "
        "AgentChute is not configured."
    )
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command = context.command or ""
        if not command:
            return []

        # Quick path: only do the cloud lookup if we see an install pattern.
        # Saves the import + cache file-read on every Bash invocation.
        stripped = strip_string_args(command)
        packages = _extract_packages(stripped)
        if not packages:
            return []

        # Lazy import to avoid loading the agentchute module on cold start
        # for OSS users who don't use AgentChute.
        try:
            from agentlint.agentchute import cloud_feed
        except ImportError:
            # agentchute module not present (very old OSS install) — no-op.
            return []

        # default=set() means: with no AgentChute license, the lookup returns
        # an empty set, the `in` check below is always False, and the
        # rule fires zero violations. Self-degrading by construction.
        feed_data = cloud_feed.get("compromised-packages", default=set(), allow_network=False)
        if not feed_data:
            return []

        # Phase 19A served a flat list directly. Phase 19C wraps it in
        # {"attribution": "...", "packages": [...]} so the CC-BY-style
        # attribution rides with the payload. Accept both shapes.
        if isinstance(feed_data, dict):
            raw = feed_data.get("packages") or []
            deny_list = set(raw) if isinstance(raw, (list, tuple, set)) else set()
        elif isinstance(feed_data, (list, tuple, set)):
            deny_list = set(feed_data)
        else:
            deny_list = set()
        if not deny_list:
            return []

        violations: list[Violation] = []
        for pkg in packages:
            if pkg in deny_list:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=(
                            f"Package '{pkg}' is on the AgentChute "
                            f"compromised-packages deny list. Install blocked."
                        ),
                        severity=self.severity,
                        suggestion=(
                            "Verify the package source and version. If you "
                            "believe this is a false positive, report it at "
                            "incidents@agentchute.io. To override locally, "
                            "use AgentLint's inline-ignore directive."
                        ),
                    )
                )

        return violations
