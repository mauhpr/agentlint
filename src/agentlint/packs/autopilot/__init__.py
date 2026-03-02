"""Autopilot safety rule pack — opt-in rules for agents running autonomously."""
from agentlint.packs.autopilot.bash_rate_limiter import BashRateLimiter
from agentlint.packs.autopilot.cross_account_guard import CrossAccountGuard
from agentlint.packs.autopilot.destructive_confirmation_gate import DestructiveConfirmationGate
from agentlint.packs.autopilot.dry_run_required import DryRunRequired
from agentlint.packs.autopilot.operation_journal import OperationJournal
from agentlint.packs.autopilot.production_guard import ProductionGuard

RULES = [
    ProductionGuard(),
    DestructiveConfirmationGate(),
    DryRunRequired(),
    BashRateLimiter(),
    CrossAccountGuard(),
    OperationJournal(),
]
