# Subagent Safety

## The limitation

Claude Code's hook system fires on the **parent session only**. When a subagent is spawned (via the Agent tool), the subagent's Bash, Write, and Edit calls **do not trigger the parent's PreToolUse hooks**. This means AgentLint's blocking rules (no-secrets, production-guard, etc.) do not protect subagent actions in real time.

This is a Claude Code architectural property, not an AgentLint bug. Each subagent runs in an isolated context with its own hook system.

## What AgentLint does

AgentLint uses three mechanisms to address the subagent safety gap:

### 1. Safety briefing injection (SubagentStart)

When a subagent spawns, the `subagent-safety-briefing` rule injects a safety notice into the subagent's context via `additionalContext`. This tells the subagent:

- It is not monitored by real-time guardrails
- It should avoid destructive infrastructure commands without explicit user confirmation
- Its actions will be audited on completion

This is advisory — the subagent can still do anything, but it's aware of the constraints.

**What the subagent receives:**

The following text is injected into the subagent's context via `additionalContext`:

```
SAFETY NOTICE (AgentLint autopilot): This subagent session is not monitored by real-time
guardrails. Avoid destructive infrastructure commands (cloud resource deletion, terraform
destroy, DROP DATABASE, iptables flush, etc.) without explicit user confirmation. Actions
will be audited on completion.
```

### 2. Post-hoc transcript audit (SubagentStop)

When a subagent completes, the `subagent-transcript-audit` rule reads the subagent's JSONL transcript and scans all Bash commands for dangerous patterns:

- Destructive operations (rm -rf, DROP TABLE/DATABASE, terraform destroy)
- Cloud resource deletion (AWS, GCP, Azure)
- Firewall/network mutations (iptables flush, ufw disable)
- Production environment access
- Git destructive operations (force push, reset --hard)

Findings appear as WARNING violations and are included in the session Stop report.

**Important:** This is detective, not preventive. The actions have already happened. WARNING severity is honest about this limitation.

### 3. AgentLint's own agents are protected

The plugin's agent definitions (`doctor.md`, `fix.md`, `security-audit.md`) include `PreToolUse` frontmatter hooks that run AgentLint's blocking rules inside the subagent context. This gives real-time blocking protection specifically for AgentLint's own subagents.

## Protecting your own subagents

If you define custom `.md` agent files for Claude Code, you can add frontmatter hooks to enable AgentLint protection inside those subagents:

```yaml
---
name: my-agent
description: My custom agent
hooks:
  PreToolUse:
    - matcher: "Bash|Edit|Write"
      hooks:
        - type: command
          command: "agentlint check --event PreToolUse --project-dir \"$CLAUDE_PROJECT_DIR\""
          timeout: 5
---
```

If using the AgentLint plugin, use the plugin's resolver instead:

```yaml
hooks:
  PreToolUse:
    - matcher: "Bash|Edit|Write"
      hooks:
        - type: command
          command: "${CLAUDE_PLUGIN_ROOT}/bin/resolve-and-run.sh check --event PreToolUse --project-dir \"$CLAUDE_PROJECT_DIR\""
          timeout: 5
```

## Known limitations

- **Built-in agents** (Explore, Plan, etc.) have no `.md` files — you cannot add frontmatter hooks to them. Safety briefing + transcript audit is the only protection.
- **Third-party plugin agents** — same limitation. You cannot modify agents from plugins you don't control.
- **Transcript audit is post-hoc** — by the time the audit runs, the subagent's actions have already taken effect. WARNING severity reflects this honestly.
- **Transcript format** — the JSONL structure may vary across Claude Code versions. The parser handles common formats defensively.

## Session report

When subagents are spawned and audited, the Stop report includes a "Subagent Activity" section:

```
Subagent Activity: 2 spawned, 2 audited
  [general-purpose (abc1234)] 5 commands, 1 finding(s):
    - terraform destroy -auto-approve
  [Explore (xyz5678)] 3 commands, no findings
```
