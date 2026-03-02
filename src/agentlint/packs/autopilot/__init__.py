"""Autopilot safety rule pack — opt-in rules for agents running autonomously."""
from agentlint.packs.autopilot.production_guard import ProductionGuard

RULES = [
    ProductionGuard(),
]
