"""Autopilot safety rule pack — opt-in rules for agents running autonomously."""
from agentlint.packs.autopilot.destructive_confirmation_gate import DestructiveConfirmationGate
from agentlint.packs.autopilot.dry_run_required import DryRunRequired
from agentlint.packs.autopilot.production_guard import ProductionGuard

RULES = [
    ProductionGuard(),
    DestructiveConfirmationGate(),
    DryRunRequired(),
]
