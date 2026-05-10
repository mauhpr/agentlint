"""Security rule pack — opt-in rules for blocking Bash escape hatches."""
from agentlint.packs.security.env_credential_reference import EnvCredentialReference
from agentlint.packs.security.no_bash_file_write import NoBashFileWrite
from agentlint.packs.security.no_blocked_domain_fetch import NoBlockedDomainFetch
from agentlint.packs.security.no_compromised_action import NoCompromisedAction
from agentlint.packs.security.no_leaked_secret_pattern import NoLeakedSecretPattern
from agentlint.packs.security.no_malicious_url_fetch import NoMaliciousUrlFetch
from agentlint.packs.security.no_network_exfil import NoNetworkExfil

RULES = [
    # PreToolUse
    NoBashFileWrite(),
    NoNetworkExfil(),
    EnvCredentialReference(),
    NoLeakedSecretPattern(),     # hybrid — gitleaks-curated patterns
    NoMaliciousUrlFetch(),       # hybrid — URLhaus deny-list
    NoBlockedDomainFetch(),      # hybrid — StevenBlack/hosts deny-list
    NoCompromisedAction(),       # hybrid — GHSA Actions advisories
]
