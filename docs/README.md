---
title: AgentLint — local guardrails for AI coding agents
description: See how AgentLint checks a proposed action, explains a blocked mistake, and helps your coding agent choose a better next step. Start locally in your repository.
hide:
  - toc
---

<div class="agentlint-hero" markdown="1">

<p class="agentlint-eyebrow">LOCAL GUARDRAILS FOR AI CODING AGENTS</p>

# Catch risky actions.<br><em>Keep your agent moving.</em>

<p class="agentlint-lede">Check proposed file changes and shell commands while your agent works. Block detected secret writes, flag risky operations, and send useful feedback straight back to the agent.</p>

<div class="agentlint-actions" markdown="1">

[Get started](quickstart.md){ .md-button .md-button--primary }
[Check your integration](coverage.md){ .md-button }

</div>

<p class="agentlint-caption">Python 3.11+ · Local checks · No account required for offline rules</p>

</div>

## A blocked mistake should have a next step

<div class="agentlint-flow" markdown="1">
<div class="agentlint-step" markdown="1">

<span class="agentlint-step-number">01 / PROPOSE</span>

### The agent proposes a write

A credential is about to land in a source file. A supported pre-tool hook sends the proposal to AgentLint.

</div>
<div class="agentlint-step agentlint-step--decision" markdown="1">

<span class="agentlint-step-number">02 / CHECK</span>

### AgentLint returns a reason

The `no-secrets` rule denies the write and tells the agent to use an environment variable.

</div>
<div class="agentlint-step" markdown="1">

<span class="agentlint-step-number">03 / REVISE</span>

### The agent can correct it

The revised proposal is checked again. Resolving one finding does not bypass the rest of the policy.

</div>
</div>

A finding gives the agent a concrete correction:

```text
[no-secrets] Secret assignment detected: api_key=...
  -> Use environment variables instead of hard-coded secrets.
```

The agent can propose this instead:

```python
import os

api_key = os.environ["SERVICE_API_KEY"]
```

This illustrates a standard pre-tool check, not a guarantee that every integration sees every action. [Coverage and limitations](coverage.md) explains the boundary.

## Start in your repository

Install using [uv](https://docs.astral.sh/uv/getting-started/installation/) or [pipx](https://pipx.pypa.io/stable/installation/), then connect the agent you use:

```bash
uv tool install agentlint
cd your-project
agentlint setup claude
```

Choose `codex`, `cursor`, `gemini`, `continue`, `kimi`, or `grok` for another native integration. Restart or reload your agent; Codex also requires reviewing and trusting the hooks in `/hooks`. Make one tool call, then check observation:

```bash
agentlint status
```

Look for a recent **observed** hook call from this project. Follow the [quickstart](quickstart.md) for the smoke check, first correction, and expected results.

## Choose the next guide

<div class="agentlint-paths" markdown="1">
<div class="agentlint-path" markdown="1">

### Connect your agent

Install hooks, activate them, and verify that calls reach AgentLint.

[Quickstart](quickstart.md) · [All integrations](#agents) · [Troubleshooting](diagnostics.md)

</div>
<div class="agentlint-path" markdown="1">

### Set your project policy

Use project policy without turning normal development into a series of exceptions.

[Protect main](guides/protect-main.md) · [Fix a false positive](guides/fix-a-false-positive.md)

[Run your linters](guides/run-linters.md) · [Share required rules](guides/shared-policy.md)

</div>
</div>

## Checks that fit your project

| With standard severity | Typical behavior |
|------------------------|------------------|
| Core pre-tool rules | Block detected secret writes, plain protected-branch force-pushes, and unapproved CI edits or package publishing |
| Advisory rules | Warn on many destructive commands, test weakening, and other risky patterns |
| Language/framework packs | Add stack-specific checks when detected or explicitly enabled |
| `security` pack | Opt-in restrictions for shell file writes and network exfiltration patterns |
| `autopilot` pack | Opt-in, experimental infrastructure and production checks |

AgentLint includes 77 built-in rules in 8 packs. Some checks happen after edits or at session end; they cannot undo work. Feed-backed rules use optional cloud data. See the [rule reference](rules.md) for events, severities, examples, and options.

## Agents

| Agent or framework | Integration | Start here |
|--------------------|-------------|------------|
| Claude Code | Native hooks; optional marketplace wrapper | [Claude guide](agents/claude.md) |
| Codex | Native hooks, including multi-file `apply_patch` inspection | [Codex guide](agents/codex.md) |
| Cursor | Native tool, shell, and file hooks | [Cursor guide](agents/cursor.md) |
| Gemini CLI | Native before/after tool hooks | [Gemini guide](agents/gemini.md) |
| Continue, Kimi, Grok | Native hook adapters | [Continue](agents/continue.md) · [Kimi](agents/kimi.md) · [Grok](agents/grok.md) |
| OpenAI Agents SDK | Guardrails attached to supported tools in your code | [SDK guide](agents/openai-agents.md) |
| MCP hosts | On-demand, advisory checks | [Host setup](agents/mcp-hosts.md) |
| Your own framework | JSON decisions or Python embedding; you enforce the result | [Generic integration](agents/generic.md) |

## Watch the walkthrough

<video class="agentlint-video" controls playsinline preload="none" poster="media/agentlint-demo-poster.png" aria-label="AgentLint product overview: a blocked credential write, a correction, and setup">
  <source src="media/agentlint-demo.mp4" type="video/mp4">
  Your browser does not support embedded video. <a href="media/agentlint-demo.mp4">Download the AgentLint overview</a>.
</video>

<p class="agentlint-caption">53 seconds: a proposed mistake, a blocked write, a correction, and setup. Synthetic operations are evaluated as data; dangerous commands are never executed.</p>

## Using AgentLint

- [Rules](rules.md) — what triggers each check and how to respond
- [Configuration](configuration.md) — packs, severity, paths, and exceptions
- [Approvals and evidence](approvals-and-evidence.md) — human decisions and verification receipts
- [Diagnostics](diagnostics.md) — check observation and investigate a finding
- [CI](ci.md) — check file changes on pull requests
- [MCP server](mcp.md) — check content, patches, and events on demand
- [AgentChute](agentchute.md) — optional cloud features and what is sent
- [CLI reference](cli.md) — generated command and option reference

## Extending AgentLint

Start with a [custom rule](custom-rules.md) for a repository convention. Use [custom adapters](custom-adapters.md) to connect a new host, [architecture](architecture.md) to understand the engine, and [subagent safety](subagent-safety.md) when configuring delegated work.

<div class="agentlint-boundary" markdown="1">

AgentLint uses rules and heuristics. It can miss behavior, flag legitimate actions, and be bypassed by a process with broad access. Keep code review, tests, CI, and least-privilege credentials in place. [Understand the security boundary](coverage.md#security-boundary).

</div>

## Read more

- [Catch risky AI coding actions before they reach your repository](https://medium.com/@mauricio_perez_r/catch-risky-ai-coding-actions-before-they-reach-your-repository-92ac1197ee31) — the action and feedback loop.
- [Your coding agent needs a stopping rule](https://medium.com/@mauricio_perez_r/your-coding-agent-needs-a-stopping-rule-330bffdea890) — completion contracts and bounded repairs with ConstraintLoop.
- [Your AI agent says it's done. What proves it?](https://medium.com/@mauricio_perez_r/your-ai-agent-says-its-done-what-proves-it-cd945ac8c68e) — verification through delivery and acceptance.

[GitHub](https://github.com/mauhpr/agentlint) · [Releases](https://github.com/mauhpr/agentlint/releases) · [Changelog](https://github.com/mauhpr/agentlint/blob/main/CHANGELOG.md)
