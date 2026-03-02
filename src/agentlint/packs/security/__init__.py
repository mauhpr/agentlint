"""Security rule pack — opt-in rules for blocking Bash escape hatches."""
from agentlint.packs.security.env_credential_reference import EnvCredentialReference
from agentlint.packs.security.no_bash_file_write import NoBashFileWrite
from agentlint.packs.security.no_network_exfil import NoNetworkExfil

RULES = [
    # PreToolUse
    NoBashFileWrite(),
    NoNetworkExfil(),
    EnvCredentialReference(),
]
