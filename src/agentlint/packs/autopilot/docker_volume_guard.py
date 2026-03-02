"""Rule: warn/block dangerous Docker volume and privileged container operations."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Each tuple: (compiled_regex, label, severity).
_DOCKER_RISKY_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    # Volume deletion (data loss) — WARNING.
    (re.compile(r"\bdocker\s+volume\s+(?:rm|remove)\b", re.I), "docker volume rm (permanent data loss)", Severity.WARNING),
    (re.compile(r"\bdocker\s+volume\s+prune\b", re.I), "docker volume prune (removes all unused volumes)", Severity.WARNING),
    # Force remove running containers — WARNING.
    (re.compile(r"\bdocker\s+(?:container\s+)?rm\s+(?:-f|--force)\b", re.I), "docker rm -f (force removes running containers)", Severity.WARNING),
    # Privileged / host-namespace — ERROR (container escape risk).
    (re.compile(r"\bdocker\s+run\b.*--privileged\b", re.I), "docker run --privileged (full host access)", Severity.ERROR),
    (re.compile(r"\bdocker\s+run\b.*--pid=host\b", re.I), "docker run --pid=host (host PID namespace)", Severity.ERROR),
    (re.compile(r"\bdocker\s+run\b.*--network=host\b", re.I), "docker run --network=host", Severity.WARNING),
    (re.compile(r"\bdocker\s+run\b.*-v\s+/var/run/docker\.sock", re.I), "docker.sock mount (host root access via socket)", Severity.ERROR),
    (re.compile(r"\bdocker\s+run\b.*-v\s+/:/", re.I), "root filesystem mount into container", Severity.ERROR),
]


class DockerVolumeGuard(Rule):
    """Warn/block dangerous Docker volume and privileged container operations."""

    id = "docker-volume-guard"
    description = "Blocks privileged Docker containers; warns on volume deletion and force-remove"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        rule_config = context.config.get(self.id, {})
        allowed_ops: list[str] = rule_config.get("allowed_ops", [])

        for pattern, label, sev in _DOCKER_RISKY_PATTERNS:
            if label in allowed_ops:
                continue
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Dangerous Docker operation detected: {label}",
                        severity=sev,
                        suggestion=(
                            "Privileged containers or volume deletion can cause data loss or container escape. "
                            "Review carefully before proceeding. "
                            "Add to docker-volume-guard.allowed_ops in agentlint.yml to permanently allow."
                        ),
                    )
                ]

        return []
