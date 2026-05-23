"""Universal rule pack — PreToolUse, PostToolUse, and Stop rules."""
from agentlint.packs.universal.cicd_pipeline_guard import CicdPipelineGuard
from agentlint.packs.universal.cli_integration import CliIntegration
from agentlint.packs.universal.dependency_hygiene import DependencyHygiene
from agentlint.packs.universal.no_compromised_dependency import NoCompromisedDependency
from agentlint.packs.universal.no_nvd_critical_cve_install import (
    NoNvdCriticalCveInstall,
)
from agentlint.packs.universal.no_vulnerable_import import NoVulnerableImport
from agentlint.packs.universal.no_vulnerable_version_install import (
    NoVulnerableVersionInstall,
)
from agentlint.packs.universal.file_scope import FileScope
from agentlint.packs.universal.drift_detector import DriftDetector
from agentlint.packs.universal.git_checkpoint import GitCheckpoint
from agentlint.packs.universal.max_file_size import MaxFileSize
from agentlint.packs.universal.no_debug_artifacts import NoDebugArtifacts
from agentlint.packs.universal.no_destructive_commands import NoDestructiveCommands
from agentlint.packs.universal.no_env_commit import NoEnvCommit
from agentlint.packs.universal.no_force_push import NoForcePush
from agentlint.packs.universal.no_push_to_main import NoPushToMain
from agentlint.packs.universal.no_secrets import NoSecrets
from agentlint.packs.universal.no_skip_hooks import NoSkipHooks
from agentlint.packs.universal.no_test_weakening import NoTestWeakening
from agentlint.packs.universal.no_todo_left import NoTodoLeft
from agentlint.packs.universal.package_publish_guard import PackagePublishGuard
from agentlint.packs.universal.test_with_changes import TestWithChanges
from agentlint.packs.universal.token_budget import TokenBudget
from agentlint.packs.universal.token_burn_against_team_budget import (
    TokenBurnAgainstTeamBudget,
)

RULES = [
    # PreToolUse
    NoSecrets(),
    NoEnvCommit(),
    NoForcePush(),
    NoPushToMain(),
    NoSkipHooks(),
    NoDestructiveCommands(),
    DependencyHygiene(),
    NoCompromisedDependency(),  # hybrid rule — uses cloud_feed deny list
    NoVulnerableVersionInstall(),  # hybrid rule — GHSA version-range filter
    NoVulnerableImport(),  # hybrid rule — GHSA import-time advisory warning
    NoNvdCriticalCveInstall(),  # hybrid rule — NVD critical CVE CPE exact match
    NoTestWeakening(),
    GitCheckpoint(),  # disabled by default — opt in via config
    CicdPipelineGuard(),
    FileScope(),
    PackagePublishGuard(),
    # PostToolUse
    CliIntegration(),
    MaxFileSize(),
    DriftDetector(),
    TokenBudget(),
    TokenBurnAgainstTeamBudget(),  # hybrid rule — uses cloud_feed for team budget
    # Stop (TokenBudget and GitCheckpoint also fire on Stop)
    NoDebugArtifacts(),
    NoTodoLeft(),
    TestWithChanges(),
]
