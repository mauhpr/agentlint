"""Shared dangerous command patterns for autopilot pack rules.

These broad-match patterns are used by the subagent transcript audit for post-hoc
detection.  PreToolUse blocking rules (cloud_resource_deletion, destructive_confirmation_gate,
etc.) keep their own precision patterns with per-operation confirmation keys.
"""
from __future__ import annotations

import re

# Each tuple: (compiled_regex, human-readable label).
DANGEROUS_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Destructive filesystem ops
    (re.compile(r"\brm\s+-[^\s]*r[^\s]*f|\brm\s+-[^\s]*f[^\s]*r", re.I), "recursive force delete"),
    # SQL destructive
    (re.compile(r"\bDROP\s+(?:TABLE|DATABASE)\b", re.I), "DROP TABLE/DATABASE"),
    # Infrastructure teardown
    (re.compile(r"\bterraform\s+destroy\b", re.I), "terraform destroy"),
    (re.compile(r"\bkubectl\s+delete\s+namespace\b", re.I), "kubectl delete namespace"),
    # Cloud resource deletion (broad match)
    (re.compile(r"\baws\b.*(?:\bdelete\b|\brm\b)", re.I), "AWS resource deletion"),
    (re.compile(r"\bgcloud\b.*\bdelete\b", re.I), "GCP resource deletion"),
    (re.compile(r"\baz\b.*\bdelete\b", re.I), "Azure resource deletion"),
    (re.compile(r"\bheroku\s+apps?:destroy\b", re.I), "Heroku app destroy"),
    # Firewall / network mutations
    (re.compile(r"\biptables\s+-F\b", re.I), "iptables flush"),
    (re.compile(r"\bufw\s+disable\b", re.I), "ufw disable"),
    # Production environment targeting
    (re.compile(r"\b(?:psql|mysql)\b.*(?:prod(?:uction)?|live)[-.]", re.I), "production database access"),
    # Git destructive
    (re.compile(r"\bgit\s+push\b.*--force\b", re.I), "git force push"),
    (re.compile(r"\bgit\s+reset\s+--hard\b", re.I), "git reset --hard"),
]
