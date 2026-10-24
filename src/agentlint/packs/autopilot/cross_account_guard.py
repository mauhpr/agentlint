"""Rule: warn when the agent switches between cloud accounts/projects within a session."""

from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.utils.shell import executable_operations, executable_words

_BASH_TOOLS = {"Bash"}

_GCLOUD_PROJECT_RE = re.compile(r"--project[=\s]+(\S+)", re.IGNORECASE)
_AWS_PROFILE_RE = re.compile(r"(?:--profile\s+(\S+)|AWS_PROFILE\s*=\s*(\S+))", re.IGNORECASE)


def _extract_gcloud_project(command: str) -> str | None:
    m = _GCLOUD_PROJECT_RE.search(command)
    if not m:
        return None
    # Strip quotes and trailing shell metacharacters like ) ; | &
    return m.group(1).strip("'\"").rstrip(");|&").lower() or None


def _extract_aws_profile(command: str) -> str | None:
    m = _AWS_PROFILE_RE.search(command)
    if m:
        return (m.group(1) or m.group(2) or "").strip("'\"").rstrip(");|&").lower() or None
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

        ca = context.session_state.setdefault(
            "cross_account",
            {
                "seen_gcloud_projects": [],
                "seen_aws_profiles": [],
            },
        )

        violations: list[Violation] = []

        operations = executable_operations(command, {"aws", "gcloud"})
        targets: list[tuple[str, str]] = []
        if operations is None:
            # Opaque execution contexts retain conservative recognition.
            targets = [
                (kind, value)
                for kind, value in (
                    (
                        "gcloud",
                        _extract_gcloud_project(command)
                        if re.search(r"\bgcloud\b", command)
                        else None,
                    ),
                    (
                        "aws",
                        _extract_aws_profile(command) if re.search(r"\baws\b", command) else None,
                    ),
                )
                if value
            ]
        else:
            for operation in operations:
                words = executable_words(list(operation.words)) or []
                prefix = list(operation.words[: len(operation.words) - len(words)]) if words else []
                env_profile = next(
                    (
                        w.partition("=")[2].lower()
                        for w in reversed(prefix)
                        if w.startswith("AWS_PROFILE=")
                    ),
                    None,
                )
                if not words:
                    continue
                binary = words[0].rsplit("/", 1)[-1]
                flag = "--project" if binary == "gcloud" else "--profile"
                value = _flag_value(words[1:], flag)
                if binary == "aws":
                    value = value or env_profile
                if value:
                    targets.append((binary, value))

        for binary, value in targets:
            key = "seen_gcloud_projects" if binary == "gcloud" else "seen_aws_profiles"
            label = "GCloud project" if binary == "gcloud" else "AWS profile"
            seen = ca.setdefault(key, [])
            if seen and value not in seen:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"{label} switch detected: {seen[-1]} → {value}",
                        severity=self.severity,
                        operation=f"{binary} account selector",
                        suggestion=f"Verify this switch is intentional. Previous {label.lower()}: {seen[-1]}",
                    )
                )
            if value not in seen:
                seen.append(value)

        return violations


def _flag_value(words: list[str], flag: str) -> str | None:
    for index, word in enumerate(words):
        if word.startswith(flag + "="):
            return word[len(flag) + 1 :].lower() or None
        if word == flag and index + 1 < len(words):
            return words[index + 1].lower() or None
    return None
