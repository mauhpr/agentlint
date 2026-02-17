"""Universal rule pack — PreToolUse, PostToolUse, and Stop rules."""
from agentlint.packs.universal.dependency_hygiene import DependencyHygiene
from agentlint.packs.universal.drift_detector import DriftDetector
from agentlint.packs.universal.max_file_size import MaxFileSize
from agentlint.packs.universal.no_debug_artifacts import NoDebugArtifacts
from agentlint.packs.universal.no_destructive_commands import NoDestructiveCommands
from agentlint.packs.universal.no_env_commit import NoEnvCommit
from agentlint.packs.universal.no_force_push import NoForcePush
from agentlint.packs.universal.no_secrets import NoSecrets
from agentlint.packs.universal.no_todo_left import NoTodoLeft
from agentlint.packs.universal.test_with_changes import TestWithChanges

RULES = [
    # PreToolUse
    NoSecrets(),
    NoEnvCommit(),
    NoForcePush(),
    NoDestructiveCommands(),
    DependencyHygiene(),
    # PostToolUse
    MaxFileSize(),
    DriftDetector(),
    # Stop
    NoDebugArtifacts(),
    NoTodoLeft(),
    TestWithChanges(),
]
