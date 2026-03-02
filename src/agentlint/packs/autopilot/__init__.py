"""Autopilot safety rule pack — opt-in rules for agents running autonomously."""
from agentlint.packs.autopilot.bash_rate_limiter import BashRateLimiter
from agentlint.packs.autopilot.cloud_infra_mutation import CloudInfraMutation
from agentlint.packs.autopilot.cloud_paid_resource_creation import CloudPaidResourceCreation
from agentlint.packs.autopilot.cloud_resource_deletion import CloudResourceDeletion
from agentlint.packs.autopilot.cross_account_guard import CrossAccountGuard
from agentlint.packs.autopilot.destructive_confirmation_gate import DestructiveConfirmationGate
from agentlint.packs.autopilot.docker_volume_guard import DockerVolumeGuard
from agentlint.packs.autopilot.dry_run_required import DryRunRequired
from agentlint.packs.autopilot.network_firewall_guard import NetworkFirewallGuard
from agentlint.packs.autopilot.operation_journal import OperationJournal
from agentlint.packs.autopilot.production_guard import ProductionGuard
from agentlint.packs.autopilot.system_scheduler_guard import SystemSchedulerGuard

RULES = [
    ProductionGuard(),
    DestructiveConfirmationGate(),
    DryRunRequired(),
    BashRateLimiter(),
    CrossAccountGuard(),
    OperationJournal(),
    CloudResourceDeletion(),
    CloudInfraMutation(),
    CloudPaidResourceCreation(),
    SystemSchedulerGuard(),
    NetworkFirewallGuard(),
    DockerVolumeGuard(),
]
