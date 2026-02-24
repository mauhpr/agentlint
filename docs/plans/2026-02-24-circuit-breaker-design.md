# Circuit Breaker Design — "Progressive Trust"

**Date:** 2026-02-24
**Version target:** 0.6.0
**Status:** Approved

## Problem

When AgentLint has a false positive bug in a blocking rule (ERROR severity), the agent gets stuck in a loop — every tool call is blocked, the agent can't make progress, and the user has to manually intervene. This happened twice in real sessions:

1. **v0.5.2**: `no-bash-file-write` flagged `$(cat <<'EOF')` heredoc command substitution as file writes
2. **v0.5.3**: `no-destructive-commands` flagged `2>/dev/null | pipe` as a fork bomb

A guardrail tool that breaks the agent is worse than no guardrails at all.

## Design Principle

**Never let a safety mechanism become the thing that breaks the system.** Same principle as Kubernetes liveness probes, Envoy circuit breakers, and AWS WAF rate limiting.

## Solution: Three-Layer Progressive Trust

### Layer 1 — Per-rule fire tracking (always on, zero config)

Every rule automatically tracks its fire count in session state. No config needed. Invisible bookkeeping that enables Layers 2 and 3.

### Layer 2 — Automatic degradation (ON by default, opt-out)

After a configurable threshold, a rule degrades from blocking to advisory:

| State | Behavior | Default Threshold |
|-------|----------|-------------------|
| **ACTIVE** | Normal — rule blocks as designed | 0-2 fires |
| **DEGRADED** | ERROR -> WARNING (visible, stops blocking) | 3rd fire |
| **PASSIVE** | WARNING -> INFO (minimal noise) | 6th fire |
| **OPEN** | Suppressed entirely (only in session report) | 10th fire |

**Why ON by default:**
- New users who hit a false positive will uninstall and never come back
- v0.5.3 proved blocking was broken for months and nobody noticed — blast radius of false blocks >> false allows
- Security-conscious users can set `circuit_breaker: { enabled: false }`

**Reset conditions** (any of):
- 5 consecutive PreToolUse evaluations where the rule does NOT fire
- 30 minutes since last fire
- Manual: `agentlint reset-circuit-breaker`

### Layer 3 — Session report transparency

At Stop, the report includes a "Circuit Breaker Activity" section: which rules were degraded, how many times they fired, current state. Full transparency.

## Security-Critical Rules

`no-secrets` and `no-env-commit` have circuit breaker **disabled by default** — these are too important to auto-degrade. Users must explicitly enable CB for them.

## State Machine

```
ACTIVE --(N fires >= degraded_after)--> DEGRADED --(N >= passive_after)--> PASSIVE --(N >= open_after)--> OPEN
  ^                                        |                                  |                            |
  |                                        |                                  |                            |
  +---- reset (clean evals OR time window) +----------------------------------+----------------------------+
```

## Session State Schema

```json
{
  "circuit_breaker": {
    "no-destructive-commands": {
      "fire_count": 5,
      "clean_count": 0,
      "first_fire_ts": 1708710000,
      "last_fire_ts": 1708710120,
      "state": "degraded",
      "transitions": [
        {"from": "active", "to": "degraded", "at_count": 3, "ts": 1708710090}
      ]
    }
  }
}
```

## Configuration

```yaml
# agentlint.yml — global defaults
circuit_breaker:
  enabled: true
  degraded_after: 3
  passive_after: 6
  open_after: 10
  reset_after_clean: 5
  reset_after_minutes: 30

# Per-rule override
rules:
  no-secrets:
    circuit_breaker: { enabled: false }   # default for security rules
  no-destructive-commands:
    circuit_breaker: { degraded_after: 5 }  # more patient
```

## Agent Communication

When degradation happens, the systemMessage tells the agent:

```
AgentLint: no-destructive-commands has fired 3 times this session and is no longer blocking.
Possible false positive — review manually. Violation: ...
```

## Files to Create/Modify

| File | Action | Est. Lines |
|------|--------|-----------|
| `src/agentlint/circuit_breaker.py` | CREATE | ~120 |
| `src/agentlint/engine.py` | Modify | +8 |
| `src/agentlint/config.py` | Modify | +12 |
| `src/agentlint/reporter.py` | Modify | +20 |
| `tests/test_circuit_breaker.py` | CREATE | ~200 |
| `CHANGELOG.md` | Update | +25 |
| `pyproject.toml` | Version 0.5.3 -> 0.6.0 | 1 |
| `plugin/.claude-plugin/plugin.json` | Version bump | 1 |
