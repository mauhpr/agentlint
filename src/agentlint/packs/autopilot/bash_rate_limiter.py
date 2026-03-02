"""Rule: circuit-break runaway destructive Bash command loops."""
from __future__ import annotations

import re
import time

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

_DESTRUCTIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+-[^\s]*r[^\s]*f|\brm\s+-[^\s]*f[^\s]*r", re.IGNORECASE),
    re.compile(r"\bDROP\s+(?:TABLE|DATABASE)\b", re.IGNORECASE),
    re.compile(r"\bkubectl\s+delete\b", re.IGNORECASE),
    re.compile(r"\bterraform\s+destroy\b", re.IGNORECASE),
    re.compile(r"\bgcloud\b.*\bdelete\b", re.IGNORECASE),
    re.compile(r"\baws\b.*\bdelete\b", re.IGNORECASE),
    re.compile(r"\bheroku\b.*\bdestroy\b", re.IGNORECASE),
]

_DEFAULT_MAX = 5
_DEFAULT_WINDOW = 300  # seconds


def _is_destructive(command: str) -> bool:
    return any(p.search(command) for p in _DESTRUCTIVE_PATTERNS)


class BashRateLimiter(Rule):
    """Block further execution after too many destructive commands in a time window."""

    id = "bash-rate-limiter"
    description = "Circuit-breaks after N destructive commands within a time window"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        if not _is_destructive(command):
            return []

        rule_config = context.config.get(self.id, {})
        max_ops = rule_config.get("max_destructive_ops", _DEFAULT_MAX)
        window_secs = rule_config.get("window_seconds", _DEFAULT_WINDOW)

        rl = context.session_state.setdefault("rate_limiter", {
            "destructive_count": 0,
            "window_start": time.time(),
        })

        now = time.time()
        # Reset window if expired
        if now - rl.get("window_start", now) >= window_secs:
            rl["destructive_count"] = 0
            rl["window_start"] = now

        # Check limit BEFORE incrementing
        if rl.get("destructive_count", 0) >= max_ops:
            return [
                Violation(
                    rule_id=self.id,
                    message=(
                        f"Rate limit exceeded: {rl['destructive_count']} destructive commands "
                        f"in {window_secs}s window (max={max_ops})"
                    ),
                    severity=self.severity,
                    suggestion="The agent has executed too many destructive operations. Review session state and reset manually if intentional.",
                )
            ]

        # Increment after passing the check
        rl["destructive_count"] = rl.get("destructive_count", 0) + 1
        return []
