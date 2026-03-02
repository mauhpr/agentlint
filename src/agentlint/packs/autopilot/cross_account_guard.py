"""Rule: warn when the agent switches between cloud accounts/projects within a session."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

_GCLOUD_PROJECT_RE = re.compile(r"--project[=\s]+(\S+)", re.IGNORECASE)
_AWS_PROFILE_RE = re.compile(r"(?:--profile\s+(\S+)|AWS_PROFILE\s*=\s*(\S+))", re.IGNORECASE)


def _extract_gcloud_project(command: str) -> str | None:
    m = _GCLOUD_PROJECT_RE.search(command)
    return m.group(1).strip("'\"").lower() if m else None


def _extract_aws_profile(command: str) -> str | None:
    m = _AWS_PROFILE_RE.search(command)
    if m:
        return (m.group(1) or m.group(2) or "").strip("'\"").lower() or None
    return None


class CrossAccountGuard(Rule):
    """Warn when the agent switches between different cloud accounts/projects in a session."""

    id = "cross-account-guard"
    description = "Warns on cloud account/project switches within the same session"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        ca = context.session_state.setdefault("cross_account", {
            "seen_gcloud_projects": [],
            "seen_aws_profiles": [],
        })

        violations: list[Violation] = []

        project = _extract_gcloud_project(command)
        if project:
            seen = ca.setdefault("seen_gcloud_projects", [])
            if seen and project not in seen:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"GCloud project switch detected: {seen[-1]} → {project}",
                        severity=self.severity,
                        suggestion="Verify this project switch is intentional. Previous project: " + seen[-1],
                    )
                )
            if project not in seen:
                seen.append(project)

        profile = _extract_aws_profile(command)
        if profile:
            seen = ca.setdefault("seen_aws_profiles", [])
            if seen and profile not in seen:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"AWS profile switch detected: {seen[-1]} → {profile}",
                        severity=self.severity,
                        suggestion="Verify this profile switch is intentional. Previous profile: " + seen[-1],
                    )
                )
            if profile not in seen:
                seen.append(profile)

        return violations
