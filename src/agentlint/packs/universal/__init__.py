"""Universal rule pack — PreToolUse rules."""
from agentlint.packs.universal.dependency_hygiene import DependencyHygiene
from agentlint.packs.universal.no_destructive_commands import NoDestructiveCommands
from agentlint.packs.universal.no_env_commit import NoEnvCommit
from agentlint.packs.universal.no_force_push import NoForcePush
from agentlint.packs.universal.no_secrets import NoSecrets

RULES = [
    NoSecrets(),
    NoEnvCommit(),
    NoForcePush(),
    NoDestructiveCommands(),
    DependencyHygiene(),
]
