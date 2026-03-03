"""Rule: inject safety context into subagent sessions."""
from __future__ import annotations

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_SAFETY_MESSAGE = (
    "SAFETY NOTICE (AgentLint autopilot): This subagent session is not monitored "
    "by real-time guardrails. Avoid destructive infrastructure commands (cloud resource "
    "deletion, terraform destroy, DROP DATABASE, iptables flush, etc.) without explicit "
    "user confirmation. Actions will be audited on completion."
)


class SubagentSafetyBriefing(Rule):
    """Inject safety context when a subagent spawns and record the spawn."""

    id = "subagent-safety-briefing"
    description = "Injects safety notice into subagent context on spawn"
    severity = Severity.INFO
    events = [HookEvent.SUB_AGENT_START]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        # Record spawn in session state for tracking
        spawned = context.session_state.setdefault("subagents_spawned", [])
        entry = {
            "agent_type": context.agent_type or "unknown",
            "agent_id": context.agent_id or "unknown",
        }
        spawned.append(entry)

        return [
            Violation(
                rule_id=self.id,
                message=_SAFETY_MESSAGE,
                severity=self.severity,
            )
        ]
