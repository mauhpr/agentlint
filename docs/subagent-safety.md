---
description: Verify Claude Code subagent hook coverage and understand AgentLint's supplemental briefings and retrospective audits.
---

# Subagent safety (Claude Code)

> This page applies to **Claude Code only**. Subagents, `SubagentStart` /
> `SubagentStop` hooks, frontmatter hooks in agent `.md` files and the plugin
> resolver are Claude Code features. For Claude Code setup see
> [agents/claude.md](agents/claude.md); other agents have their own pages listed
> in [docs/README.md](README.md).
>
> Hook behaviour for subagents depends on your Claude Code version. Check the
> [Claude Code subagent documentation](https://code.claude.com/docs/en/sub-agents#define-hooks-for-subagents)
> for the version you run, and use `agentlint status` to inspect observed hook events.

Start with [Claude Code setup](agents/claude.md), then verify your subagent workflow separately. A check observed in the parent session does not establish that a particular child tool call was checked. The [coverage guide](coverage.md) explains what observation can and cannot prove.

## The limitation

Current Claude Code documentation says session-wide settings and plugin hooks also run for subagent tool calls. Frontmatter hooks add checks scoped to an individual agent. The older claim that parent hooks never run inside subagents does not describe the current documented behavior.

Actual AgentLint coverage still depends on the host version, trusted hook configuration, tool matchers, and events received. Do not use a lifecycle event such as `SubagentStart` as evidence that every later Bash or file action was intercepted.

## What AgentLint does

AgentLint provides supplemental subagent mechanisms. The first
two are rules in the `autopilot` pack, which is opt-in and experimental; add
`autopilot` to `packs:` to enable them (see [`subagent-safety-briefing`](rules.md#subagent-safety-briefing) and
[`subagent-transcript-audit`](rules.md#subagent-transcript-audit)).

### 1. Safety briefing injection (SubagentStart)

When a subagent spawns, the `subagent-safety-briefing` rule injects a safety notice into the subagent's context via `additionalContext`. This tells the subagent:

- It is not monitored by real-time guardrails
- It should avoid destructive infrastructure commands without explicit user confirmation
- Its actions will be audited on completion

The briefing is advisory. It does not deny actions; host permissions and matching tool hooks apply separately.

The notice in AgentLint 2.10.1 retains conservative wording about missing real-time monitoring. It is a static rule message, not a runtime measurement of the host's hook coverage. Verify the installed hooks rather than treating that sentence as a coverage diagnosis.

**What the subagent receives:**

The following text is injected into the subagent's context via `additionalContext`:

```
SAFETY NOTICE (AgentLint autopilot): This subagent session is not monitored by real-time
guardrails. Avoid destructive infrastructure commands (cloud resource deletion, terraform
destroy, DROP DATABASE, iptables flush, etc.) without explicit user confirmation. Actions
will be audited on completion.
```

### 2. Post-hoc transcript audit (SubagentStop)

When a subagent completes, the `subagent-transcript-audit` rule reads an available JSONL transcript and checks Bash commands extracted from supported entries for dangerous patterns:

- Destructive operations (rm -rf, DROP TABLE/DATABASE, terraform destroy)
- Cloud resource deletion (AWS, GCP, Azure)
- Firewall/network mutations (iptables flush, ufw disable)
- Production environment access
- Git destructive operations (force push, reset --hard)

Findings appear as WARNING violations and are included in the session Stop report.

The audit runs after execution and cannot prevent the recorded actions. Its WARNING severity reflects that timing.

### 3. AgentLint's own agents are protected

The Claude Code plugin's agent definitions ([mauhpr/agentlint-plugin](https://github.com/mauhpr/agentlint-plugin): `agents/doctor.md`, `agents/fix.md`, `agents/security-audit.md`) include `PreToolUse` frontmatter hooks for their own tool calls. These are additional configured checks, alongside applicable session-wide hooks. They depend on the resolver working and the host accepting and running the hook definitions.

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

- **Host behavior changes** — current session-wide hook behavior does not establish coverage in older Claude Code installations. Verify the version and the workflow you run.
- **Built-in and third-party agents** — you may not control their frontmatter. Applicable session-wide hooks can still run; do not assume that a briefing or transcript audit is their only possible check.
- **Frontmatter trust** — Claude Code can skip hooks in untrusted project agent definitions. Follow the host's trust instructions before relying on them.
- **Transcript audit is post-hoc** — by the time the audit runs, the subagent's actions have already taken effect. WARNING severity reflects this honestly.
- **Transcript availability** — auditing requires a readable transcript path from the host. Transcripts over 1 MiB are skipped, as are individual JSONL lines over 100,000 characters. Supported transcript shapes are scanned for Bash tool commands; a clean result is not proof that every action was examined.

## Session report

When subagents are spawned and audited, the Stop report includes a "Subagent Activity" section:

```
Subagent Activity: 2 spawned, 2 audited
  [general-purpose (abc1234)] 5 commands, 1 finding(s):
    - terraform destroy -auto-approve
  [Explore (xyz5678)] 3 commands, no findings
```
