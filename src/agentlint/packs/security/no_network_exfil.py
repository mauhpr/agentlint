"""Rule: detect potential network exfiltration via Bash commands."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# --- Exfiltration patterns ---
# Each tuple: (compiled_regex, human-readable label).
_EXFIL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # curl POST/PUT with data or file upload.
    (re.compile(
        r"\bcurl\b.*(?:-X\s*(?:POST|PUT)\s.*-[dF@]|-[dF@]\s.*-X\s*(?:POST|PUT))",
        re.IGNORECASE,
    ), "curl POST/PUT with data"),
    # curl with -d @file (file upload).
    (re.compile(r"\bcurl\b.*-d\s*@\S+", re.IGNORECASE), "curl -d @file"),
    # Piping sensitive content to curl.
    (re.compile(r"cat\s+\S*(?:\.env|secret|credential|token|\.pem|\.key|id_rsa)\S*\s*\|.*\bcurl\b", re.IGNORECASE),
     "piping secrets to curl"),
    # netcat (nc) with input redirection from sensitive files.
    (re.compile(r"\bnc\b.*<\s*\S*(?:\.env|secret|credential|token|\.pem|\.key)", re.IGNORECASE),
     "nc < sensitive file"),
    # scp with sensitive file paths.
    (re.compile(r"\bscp\b.*(?:\.env|credential|secret|token|\.pem|\.key|id_rsa)", re.IGNORECASE),
     "scp sensitive file"),
    # wget --post-file or --post-data.
    (re.compile(r"\bwget\b.*--post-(?:file|data)", re.IGNORECASE), "wget POST"),
    # Python requests.post() one-liners.
    (re.compile(
        r"\bpython[23]?\s+-c\s+.*requests\.(?:post|put)\b",
        re.IGNORECASE,
    ), "python requests.post()"),
    # rsync to remote (contains :).
    (re.compile(
        r"\brsync\b.*(?:\.env|credential|secret|token|\.pem|\.key).*\S+:\S+",
        re.IGNORECASE,
    ), "rsync sensitive files to remote"),
]

# Default hosts that are safe for outbound data.
_DEFAULT_ALLOWED_HOSTS = frozenset({
    "github.com",
    "pypi.org",
    "registry.npmjs.org",
    "rubygems.org",
})


def _extract_host(command: str) -> str | None:
    """Try to extract the target host from a curl/wget/nc command."""
    # Look for URLs.
    url_match = re.search(r"https?://([^/:\s]+)", command)
    if url_match:
        return url_match.group(1).lower()
    # Look for host in nc commands.
    nc_match = re.search(r"\bnc\s+(\S+)\s+\d+", command)
    if nc_match:
        return nc_match.group(1).lower()
    return None


class NoNetworkExfil(Rule):
    """Detect potential data exfiltration via network commands."""

    id = "no-network-exfil"
    description = "Blocks potential data exfiltration via curl, nc, scp, etc."
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "security"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        # Load config.
        rule_config = context.config.get(self.id, {})
        allowed_hosts: list[str] = rule_config.get("allowed_hosts", [])
        all_allowed = _DEFAULT_ALLOWED_HOSTS | frozenset(h.lower() for h in allowed_hosts)

        # Check if target host is allowed.
        host = _extract_host(command)
        if host and host in all_allowed:
            return []

        for pattern, label in _EXFIL_PATTERNS:
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Potential data exfiltration detected via {label}",
                        severity=self.severity,
                        suggestion="Verify this network operation is intentional and not sending sensitive data to an external host.",
                    )
                ]

        return []
