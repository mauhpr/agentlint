"""Rule: block writes to CI/CD pipeline definition files without approval."""
from __future__ import annotations

import fnmatch

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_FILE_TOOLS = {"Write", "Edit", "MultiEdit"}

# These files run arbitrary code in CI — supply-chain risk.
_CICD_ERROR_PATTERNS = [
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".github/actions/**/*.yml",
    ".github/actions/**/*.yaml",
    ".gitlab-ci.yml",
    ".gitlab-ci.yaml",
    ".circleci/config.yml",
    ".circleci/*.yml",
    "Jenkinsfile",
    "Jenkinsfile.*",
    "azure-pipelines.yml",
    "azure-pipelines.yaml",
    "buildkite.yml",
    ".buildkite/*.yml",
    ".travis.yml",
    "cloudbuild.yaml",
    "cloudbuild.yml",
]

# Build-time impact, not a direct CI gate — WARNING only.
_CICD_WARNING_PATTERNS = [
    "Dockerfile",
    "Dockerfile.*",
    "docker-compose*.yml",
    "docker-compose*.yaml",
]


def _matches_any(path: str, patterns: list[str]) -> bool:
    """Return True if path matches any glob pattern (checked against basename and full path)."""
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        # Also match against just the filename for patterns without path separators.
        if "/" not in pattern and fnmatch.fnmatch(path.split("/")[-1], pattern):
            return True
    return False


class CicdPipelineGuard(Rule):
    """Block writes to CI/CD pipeline files without session approval."""

    id = "cicd-pipeline-guard"
    description = "Blocks edits to CI/CD pipeline files (.github/workflows, Jenkinsfile, etc.) without approval"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _FILE_TOOLS:
            return []

        file_path: str = context.file_path or ""
        if not file_path:
            return []

        rule_config = context.config.get(self.id, {})
        allowed_files: list[str] = rule_config.get("allowed_files", [])

        # Permanent bypass via config.
        if _matches_any(file_path, allowed_files):
            return []

        # Session-level approval gate.
        approved: list[str] = context.session_state.get("approved_cicd_files", [])
        if any(fnmatch.fnmatch(file_path, a) for a in approved):
            return []

        # ERROR: direct CI pipeline files.
        if _matches_any(file_path, _CICD_ERROR_PATTERNS):
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Modifying CI/CD pipeline file: {file_path}",
                    severity=Severity.ERROR,
                    file_path=file_path,
                    suggestion=(
                        f"CI/CD pipeline changes can introduce supply-chain vulnerabilities. "
                        f"To allow this file for the session, set "
                        f"session_state['approved_cicd_files'] = ['{file_path}']. "
                        f"For a permanent bypass, add to cicd-pipeline-guard.allowed_files in agentlint.yml."
                    ),
                )
            ]

        # WARNING: build-time files.
        if _matches_any(file_path, _CICD_WARNING_PATTERNS):
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Modifying build configuration file: {file_path}",
                    severity=Severity.WARNING,
                    file_path=file_path,
                    suggestion=(
                        "Changes to Dockerfiles and compose files affect the build environment. "
                        "Review for unexpected dependencies or base image changes."
                    ),
                )
            ]

        return []
