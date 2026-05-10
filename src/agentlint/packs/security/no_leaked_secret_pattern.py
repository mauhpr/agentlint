"""Rule: block writes that contain leaked-secret patterns from gitleaks.

Hybrid rule (Phase 19, security pack). Runs the cloud-curated set of
gitleaks regexes against new file content. Catches AWS keys, GH tokens,
Stripe keys, RSA private keys, and ~200 other patterns gitleaks
maintains. The pattern set is refreshed daily from gitleaks's MIT
codebase.

Why this hybrid rule and not the existing ``no-secrets`` rule:
    ``no-secrets`` (universal pack) ships ~30 hardcoded prefixes
    (AKIA, ghp_, sk_live_, etc.) — perfect for the offline, OSS-only
    case. This rule augments that with the full ~220-pattern gitleaks
    set, which catches longer-tail vendors (1Password, Adafruit,
    SendGrid, etc.) without bloating OSS package size or relying on
    gitleaks-style regex engines locally.

Self-degrading: when AgentChute isn't configured, this rule is a no-op
and the user falls back to the offline ``no-secrets`` coverage.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

logger = logging.getLogger("agentlint.security.no_leaked_secret_pattern")


_FILE_TOOLS = {"Edit", "Write"}

# Cap how many patterns we run per evaluation. The full gitleaks set is
# ~220 regexes; running all of them on every Edit/Write is fine
# performance-wise (each regex is < 1KB and Python's re is fast) but
# we cap at 500 as defense in depth against a malicious feed payload.
_MAX_PATTERNS = 500

# Cap per-rule output. 5 hits per file is plenty — past that we collapse
# into a single "5+ leaked secrets detected" message to avoid spamming
# the agent with redundant violations.
_MAX_VIOLATIONS_PER_FILE = 5


# Process-level memo of compiled patterns keyed by (rule_id, regex).
# Compiles each pattern once and reuses across all Edit/Write events
# in the same Python process. Cleared automatically when the process
# exits (no need to invalidate on feed refresh — fresh feed → new
# regex strings → new memo entries; old entries become unreachable).
_compiled_cache: dict[tuple[str, str], re.Pattern[str] | None] = {}


def _compile(pattern: str, rule_id: str) -> re.Pattern[str] | None:
    """Compile a regex with caching. Returns None if the regex is
    invalid (and logs at DEBUG so a single bad upstream pattern
    doesn't fail the rule)."""
    key = (rule_id, pattern)
    if key in _compiled_cache:
        return _compiled_cache[key]
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        logger.debug("invalid regex for %s: %s", rule_id, e)
        compiled = None  # cache the failure too
    _compiled_cache[key] = compiled
    return compiled


class NoLeakedSecretPattern(Rule):
    """Block Edit/Write of content matching cloud-curated gitleaks
    patterns. Self-degrades when AgentChute isn't configured.
    """

    id = "no-leaked-secret-pattern"
    description = (
        "Blocks writes that contain leaked-secret patterns from the "
        "AgentChute cloud-curated gitleaks ruleset. Self-degrades to "
        "no-op when AgentChute is not configured."
    )
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "security"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _FILE_TOOLS:
            return []

        content = (
            context.tool_input.get("new_string")
            or context.tool_input.get("content")
            or ""
        )
        if not content:
            return []

        # Lazy import keeps cold-start fast for OSS users not on AgentChute.
        try:
            from agentlint.agentchute import cloud_feed
        except ImportError:
            return []

        feed_data = cloud_feed.get(
            "secret-patterns",
            default={"patterns": []},
            allow_network=False,
        )
        if not isinstance(feed_data, dict):
            return []
        patterns: list[dict[str, Any]] = feed_data.get("patterns") or []
        if not patterns:
            return []
        if len(patterns) > _MAX_PATTERNS:
            patterns = patterns[:_MAX_PATTERNS]

        file_path = context.tool_input.get("file_path") or context.file_path
        violations: list[Violation] = []

        for pat in patterns:
            if len(violations) >= _MAX_VIOLATIONS_PER_FILE:
                break
            if not isinstance(pat, dict):
                continue
            rule_id = pat.get("id") or ""
            regex = pat.get("regex") or ""
            if not rule_id or not regex:
                continue

            compiled = _compile(regex, rule_id)
            if compiled is None:
                continue

            match = compiled.search(content)
            if match is None:
                continue

            severity_str = (pat.get("severity") or "HIGH").upper()
            sev = Severity.ERROR if severity_str in ("CRITICAL", "HIGH") else Severity.WARNING
            title = pat.get("title") or rule_id

            # Don't echo the matched literal; gitleaks-format secrets
            # are sensitive even in lint output. Mention only the rule
            # and a redacted match indicator.
            redacted = match.group(0)
            if len(redacted) > 8:
                redacted = redacted[:4] + "…" + redacted[-4:]
            else:
                redacted = "***"

            violations.append(
                Violation(
                    rule_id=self.id,
                    message=(
                        f"Possible {title} ({rule_id}) detected in content "
                        f"(redacted match: {redacted})"
                    ),
                    severity=sev,
                    file_path=file_path,
                    suggestion=(
                        "Move the credential to an env var or secrets manager. "
                        "If this is a test fixture, use a clearly-fake value "
                        "(e.g., 'AKIA0000000000EXAMPLE'). Override with "
                        "AgentLint's inline-ignore directive only after review."
                    ),
                )
            )

        if len(violations) == _MAX_VIOLATIONS_PER_FILE:
            # Indicate the cap was hit — see config to lift if needed.
            violations.append(
                Violation(
                    rule_id=self.id,
                    message=(
                        f"…additional matches truncated at {_MAX_VIOLATIONS_PER_FILE}; "
                        f"review the full file for further leaks."
                    ),
                    severity=Severity.WARNING,
                    file_path=file_path,
                )
            )

        return violations
