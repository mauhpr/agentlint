"""Rule: warn on ``curl/wget/fetch`` to a domain in the StevenBlack
hosts deny-list (ads/trackers/malware/etc).

Hybrid rule (Phase 19, security pack). Sibling to no-malicious-url-fetch
with a different signal:
    - ``no-malicious-url-fetch`` is ERROR — URLhaus is high-precision,
      time-sensitive, ~2K-1M URLs all confirmed malicious right now.
    - ``no-blocked-domain-fetch`` is WARNING — StevenBlack is broader
      (~80K domains across categories) and more likely to overlap with
      legitimate domains the developer's project actually depends on
      (e.g., advertiser CDNs that also host fonts).

The two rules can both fire on the same URL — that's fine. The user
sees URLhaus's ERROR plus StevenBlack's WARNING and has full context.

Self-degrading: when AgentChute isn't configured, the rule is a no-op.

Performance: the deny list is ~80K domains. We build a process-level
``set`` once on first use within a process, keyed off the feed list's
identity (so a feed refresh produces a new id and a fresh set).
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

logger = logging.getLogger("agentlint.security.no_blocked_domain_fetch")

_BASH_TOOLS = {"Bash"}

_URL_RE = re.compile(r"https?://[^\s\"'`)>]+")
_FETCH_VERBS = re.compile(
    r"\b(?:curl|wget|fetch|http|httpie|axel|aria2c)\b",
    re.IGNORECASE,
)


def _extract_fetch_urls(command: str) -> list[str]:
    """Same logic as no-malicious-url-fetch — extract URLs only when
    they appear inside a fetch-verb invocation."""
    if not command or not _FETCH_VERBS.search(command):
        return []
    cleaned: list[str] = []
    for u in _URL_RE.findall(command):
        u = u.rstrip(".,;:")
        if u:
            cleaned.append(u)
    return cleaned


# Process-level cache: (id(domains_list), set(domains))
_set_cache: tuple[int, set[str]] | None = None


def _domains_set(domains: list[str]) -> set[str]:
    global _set_cache
    sentinel = id(domains)
    if _set_cache is None or _set_cache[0] != sentinel:
        _set_cache = (sentinel, {d.lower() for d in domains if d})
    return _set_cache[1]


class NoBlockedDomainFetch(Rule):
    """WARNING-level: flag fetches to domains on StevenBlack/hosts.

    Self-degrades to no-op when AgentChute isn't configured.
    """

    id = "no-blocked-domain-fetch"
    description = (
        "Warns when `curl/wget/fetch/http` targets a domain on the "
        "AgentChute cloud-curated StevenBlack/hosts deny-list "
        "(ads/trackers/malware/etc). Self-degrades to no-op when "
        "AgentChute is not configured."
    )
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "security"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []
        command = context.command or ""
        if not command:
            return []

        urls = _extract_fetch_urls(command)
        if not urls:
            return []

        try:
            from agentlint.agentchute import cloud_feed
        except ImportError:
            return []

        feed_data = cloud_feed.get(
            "blocked-domains", default={"domains": []}, allow_network=False
        )
        if not isinstance(feed_data, dict):
            return []
        domains: list[str] = feed_data.get("domains") or []
        if not domains:
            return []

        denyset = _domains_set(domains)

        violations: list[Violation] = []
        seen_hosts: set[str] = set()
        for url in urls:
            try:
                host = (urlparse(url).netloc or "").lower()
            except ValueError:
                continue
            if not host or host in seen_hosts:
                continue
            seen_hosts.add(host)
            if host not in denyset:
                continue
            violations.append(
                Violation(
                    rule_id=self.id,
                    message=(
                        f"Fetch of {url} — domain '{host}' is on the "
                        f"StevenBlack/hosts deny-list (ads/trackers/"
                        f"malware/etc)"
                    ),
                    severity=self.severity,
                    suggestion=(
                        f"This domain is broadly blocked at the host level. "
                        f"If '{host}' is a legitimate dependency for your "
                        f"project, override locally with AgentLint's "
                        f"inline-ignore directive."
                    ),
                )
            )

        return violations
