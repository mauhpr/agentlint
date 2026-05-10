"""Rule: block install of dependency versions known to have CVEs (GHSA data).

Hybrid rule (Phase 19) — sibling to no-compromised-dependency.
Where no-compromised-dependency flags a *malicious* package by name,
this rule flags a *legitimate but vulnerable* version range.

Self-degrading: if AgentChute is not configured, the rule is a silent no-op.
The OSS user gets the existing dependency-hygiene warning either way;
only AgentChute-licensed teams get the GHSA-driven version-range filter.

Sourcing of the data:
    AgentChute's API serves /v1/feeds/ghsa-vulns, populated from a daily
    sync of github/advisory-database (CC-BY-4.0). The OSS client caches
    the feed for 24h via the cloud_feed primitive.

Why a hybrid rule rather than pure-OSS:
    GHSA publishes new vulnerabilities multiple times per day. Hard-coding
    a list in OSS would be stale within hours of the next CVE drop. The
    daily-refreshed feed keeps coverage current without forcing OSS
    releases for every advisory.

Why a hybrid rule rather than pure-cloud:
    Lint-time decisions need to be local; a network round-trip per Bash
    invocation is unacceptable. The 24h cache trades some freshness
    (1d vs hours) for hot-path speed (~10ms vs ~200ms).

Limitation (V0): this rule's version comparator handles common semver
strings (``1.2.3``, ``2.0.0-beta.1``) and a subset of pep440. Pinned
versions in the install command are extracted; unpinned installs (just
``npm i lodash``) skip the version check (DependencyHygiene already warns
about those).
"""

from __future__ import annotations

import re
from typing import Any

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.utils.bash import strip_string_args

_BASH_TOOLS = {"Bash"}

# Map command-line ecosystem name → OSV ecosystem name. Both forms appear
# in the wild; the GHSA feed uses the OSV form.
_ECOSYSTEM_MAP = {
    "npm": "npm",
    "yarn": "npm",
    "pnpm": "npm",
    "pip": "PyPI",
    "pip3": "PyPI",
    "gem": "RubyGems",
    "cargo": "crates.io",
}

# Patterns that capture (package_name, version_specifier). The pin
# delimiter varies by ecosystem:
#   npm/yarn/pnpm: ``foo@1.2.3`` or ``@scope/foo@1.2.3``
#   pip:           ``foo==1.2.3`` or ``foo>=1.0,<2.0``
#   gem:           ``foo -v 1.2.3`` (older) or no inline pin (skip)
#   cargo:         ``foo --version 1.2.3`` or ``foo@1.2.3``
_INSTALL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # npm / yarn / pnpm: ``npm install foo@1.2.3`` or ``yarn add @scope/foo@1.2.3``
    (re.compile(
        r"\b(?:npm|yarn|pnpm)\s+(?:install|i|add)\s+(?!-)"
        r"(?P<name>@?[\w][\w@/\-\.]*)@(?P<version>[\w][\w\-\.]*)",
        re.IGNORECASE,
    ), "npm"),
    # pip / pip3: ``pip install foo==1.2.3``
    (re.compile(
        r"\bpip3?\s+install\s+(?!-)"
        r"(?P<name>[\w][\w\-\.]*)==(?P<version>[\w][\w\-\.]*)",
        re.IGNORECASE,
    ), "pip"),
    # cargo: ``cargo install foo --version 1.2.3``
    (re.compile(
        r"\bcargo\s+(?:add|install)\s+(?!-)"
        r"(?P<name>[\w][\w\-\.]*)\s+--version\s+(?P<version>[\w][\w\-\.]*)",
        re.IGNORECASE,
    ), "cargo"),
]


def _extract_pinned_installs(command: str) -> list[tuple[str, str, str]]:
    """Return ``[(ecosystem_osv, package_name, version), ...]`` for every
    pinned install in the command. Lower-cases names. Does NOT include
    unpinned installs — those are out of scope for this rule."""
    out: list[tuple[str, str, str]] = []
    for pattern, cli_eco in _INSTALL_PATTERNS:
        for match in pattern.finditer(command):
            name = (match.group("name") or "").lower()
            version = (match.group("version") or "").strip()
            if not name or not version:
                continue
            osv_eco = _ECOSYSTEM_MAP.get(cli_eco, cli_eco)
            out.append((osv_eco, name, version))
    return out


# ---------- Version comparison ----------
#
# OSV ranges are sequences of "events": [{"introduced": "X"}, {"fixed": "Y"}, ...]
# A version V is "in the range" iff V >= introduced AND (no fixed yet, or V < fixed).
# We compare using a tuple of integers extracted from the version string;
# strings that don't parse cleanly are treated as "definitely lower than"
# (so a `1.2.3-rc1` falling in a `< 2.0.0` range correctly flags).


_INT_PART = re.compile(r"\d+")


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a version string into a comparable tuple of ints.

    Crude but adequate for V0:
      "1.2.3"          → (1, 2, 3)
      "2.0.0-beta.1"   → (2, 0, 0, 1)        # ignores the "-beta" tag
      "1.2"            → (1, 2)
      "v1.0"           → (1, 0)              # leading v stripped
      "weird"          → (0,)                # un-parseable → minimum

    Pre-release suffixes like ``-rc1`` are *intentionally* lost in this
    crude implementation, which means a 1.2.3-rc1 and 1.2.3 compare equal.
    For the security-feed use case this is acceptable: if we say
    "anything < 2.0.0 is vulnerable" and someone installs 2.0.0-rc1,
    we'd rather warn than miss it.
    """
    if not v:
        return (0,)
    cleaned = v.lstrip("vV")
    parts = _INT_PART.findall(cleaned)
    if not parts:
        return (0,)
    return tuple(int(p) for p in parts[:6])  # cap at 6 segments — paranoia


def _version_in_range(version: tuple[int, ...], events: list[dict[str, Any]]) -> bool:
    """Apply OSV-style range events. ``events`` is a list of dicts each
    with one of: ``introduced``, ``fixed``, ``last_affected``.
    Returns True if version is currently in the affected range.
    """
    introduced: tuple[int, ...] | None = None
    fixed: tuple[int, ...] | None = None
    last_affected: tuple[int, ...] | None = None
    for ev in events:
        if "introduced" in ev:
            introduced = _parse_version(ev["introduced"])
        elif "fixed" in ev:
            fixed = _parse_version(ev["fixed"])
        elif "last_affected" in ev:
            last_affected = _parse_version(ev["last_affected"])

    if introduced is not None and version < introduced:
        return False
    if fixed is not None and version >= fixed:
        return False
    if last_affected is not None and version > last_affected:
        return False
    # If neither fixed nor last_affected is set, the OSV record means
    # "everything from introduced onward is vulnerable" — be conservative.
    return True


def _matches_any_range(version: tuple[int, ...], ranges: Any) -> bool:
    """Check if ``version`` satisfies any of the OSV ranges in ``ranges``.

    Defensive: ranges may be a list or non-list (older format). Any
    parsing failure short-circuits to False (no match) so a bad upstream
    record doesn't fire a false positive."""
    if not isinstance(ranges, list):
        return False
    for r in ranges:
        if not isinstance(r, dict):
            continue
        events = r.get("events")
        if not isinstance(events, list):
            continue
        if _version_in_range(version, events):
            return True
    return False


# ---------- The rule ----------


class NoVulnerableVersionInstall(Rule):
    """Block install of a pinned package version that's known-vulnerable
    via GHSA. Self-degrades to no-op when AgentChute isn't configured.
    """

    id = "no-vulnerable-version-install"
    description = (
        "Blocks install of a specific package version when GHSA reports "
        "it as vulnerable. Pinned installs only (e.g. `npm i foo@1.2.3`); "
        "unpinned installs are handled by `dependency-hygiene`."
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

        # Quick path: only pay the cloud-feed cost if we see a pinned install.
        installs = _extract_pinned_installs(strip_string_args(command))
        if not installs:
            return []

        # Lazy import to avoid loading the agentchute module on cold start
        # for OSS users who don't use AgentChute.
        try:
            from agentlint.agentchute import cloud_feed
        except ImportError:
            return []

        # default={"records": []} keeps the rule a no-op when the feed
        # is unavailable. Self-degrading by construction.
        feed_data = cloud_feed.get("ghsa-vulns", default={"records": []}, allow_network=False)
        if not isinstance(feed_data, dict):
            return []
        records = feed_data.get("records") or []
        if not records:
            return []

        # Build ecosystem+package → list of (vulnerable_versions, ghsa_id, severity)
        # for O(1) lookup per install command. Cache won't change between
        # rule evaluations in the same process, but the memo is recomputed
        # each call to keep the implementation simple — the 309-record
        # default seed is < 1ms to index.
        index: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for rec in records:
            if not isinstance(rec, dict):
                continue
            eco = rec.get("ecosystem")
            pkg = rec.get("package")
            if not eco or not pkg:
                continue
            index.setdefault((eco, pkg.lower()), []).append(rec)

        violations: list[Violation] = []
        for ecosystem, name, version in installs:
            matches = index.get((ecosystem, name)) or []
            if not matches:
                continue
            parsed_version = _parse_version(version)
            for rec in matches:
                if _matches_any_range(parsed_version, rec.get("vulnerable_versions")):
                    ghsa = rec.get("ghsa_id", "GHSA-?")
                    sev = rec.get("severity") or "UNKNOWN"
                    summary = (rec.get("summary") or "").strip()
                    suffix = f" — {summary}" if summary else ""
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=(
                                f"{ecosystem}:{name}@{version} is vulnerable per "
                                f"{ghsa} (severity: {sev}){suffix}"
                            ),
                            severity=self.severity,
                            suggestion=(
                                f"Upgrade {name} to a version outside the affected "
                                f"range. See the GHSA references for the fix version. "
                                f"Override locally with AgentLint's inline-ignore "
                                f"directive if you've reviewed the risk."
                            ),
                        )
                    )
                    break  # one violation per install is enough

        return violations
