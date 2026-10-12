---
title: AgentLint — local guardrails for AI coding agents
description: Check proposed file changes and shell commands, get actionable feedback, and keep your coding agent working. Install AgentLint and connect your agent.
hide:
  - toc
---

<div class="agentlint-hero" markdown="1">

<p class="agentlint-eyebrow">LOCAL GUARDRAILS FOR AI CODING AGENTS</p>

# Catch risky actions.<br><em>Keep useful work moving.</em>

<p class="agentlint-lede">AgentLint checks proposed file changes and shell commands in supported agent workflows. It can block a risky action, explain the finding, and let the agent correct its next step.</p>

<div class="agentlint-actions" markdown="1">

[Install AgentLint](quickstart.md){ .md-button .md-button--primary }
[Explore the rules](rules.md){ .md-button }

</div>
</div>

<video class="agentlint-video" controls playsinline preload="none" poster="media/agentlint-demo-poster.png" aria-label="AgentLint product overview: a blocked credential write, a correction, and setup">
  <source src="media/agentlint-demo.mp4" type="video/mp4">
  Your browser does not support embedded video. <a href="media/agentlint-demo.mp4">Download the AgentLint overview</a>.
</video>

<p class="agentlint-caption">A 53-second overview: what AgentLint checks, one blocked write, a useful correction, and setup. The demonstration evaluates proposed operations as data; it does not execute them or claim a test pass.</p>

## Start in your repository

Install with Python 3.11 or newer, then run setup from the project you want to protect:

```bash
uv tool install agentlint
cd your-project
agentlint setup codex
```

Use `claude`, `cursor`, `gemini`, `continue`, `kimi`, or `grok` for another native
integration. Restart your agent, follow its hook trust instructions, and make a
tool call before checking observation:

```bash
agentlint status
```

The [quickstart](quickstart.md) walks through installation and a first block.
The [agent setup guides](README.md#agents) explain each integration's coverage
and verification steps.

## A blocked mistake should have a next step

A proposed credential assignment in a source file can produce this finding:

```text
[no-secrets] Secret assignment detected: api_key=...
  -> Use environment variables instead of hard-coded secrets.
```

The agent receives a concrete correction while it is still working. It can
revise the proposed change to read a credential from the environment, then let
AgentLint evaluate the new action. Under standard severity, errors block;
warnings advise. Integration coverage varies by agent.

## Choose the next guide

<div class="agentlint-paths" markdown="1">
<div class="agentlint-path" markdown="1">

### Connect your agent

Start with the native setup and confirm that AgentLint receives hook calls.

[Claude Code](agents/claude.md) · [Codex](agents/codex.md) ·
[Cursor](agents/cursor.md) · [Gemini CLI](agents/gemini.md)

[All integrations](README.md#agents)

</div>
<div class="agentlint-path" markdown="1">

### Set your project policy

Inspect the rules, tune paths and options, and use the same checks in CI.

[Rules](rules.md) · [Configuration](configuration.md) ·
[CI](ci.md) · [Diagnostics](diagnostics.md)

</div>
</div>

## Agents

How to connect each coding agent, what gets checked and how to verify it.

| Agent | Guide | Integration |
|-------|-------|-------------|
| Claude Code | [agents/claude.md](agents/claude.md) | Native hooks (also available as a [marketplace plugin](https://github.com/mauhpr/agentlint-plugin)) |
| Codex | [agents/codex.md](agents/codex.md) | Native hooks, including `apply_patch` inspection |
| Cursor | [agents/cursor.md](agents/cursor.md) | Native hooks |
| Gemini CLI | [agents/gemini.md](agents/gemini.md) | Native hooks |
| Continue | [agents/continue.md](agents/continue.md) | Native hooks |
| Kimi Code CLI | [agents/kimi.md](agents/kimi.md) | Native hooks |
| Grok CLI | [agents/grok.md](agents/grok.md) | Native hooks |
| OpenAI Agents SDK | [agents/openai-agents.md](agents/openai-agents.md) | Guardrail code |
| MCP hosts | [agents/mcp-hosts.md](agents/mcp-hosts.md) | MCP server |
| Anything else | [agents/generic.md](agents/generic.md) | JSON in, decision out |

## Checks that fit your project

Core packs cover common file and command patterns. Language packs add project
checks; the security pack is opt-in, and the autopilot pack is experimental.
Examples include hard-coded secrets, destructive commands, test weakening,
and CI configuration changes. The [rule reference](rules.md) lists their exact
scope and options.

Hook checks run locally. The [optional AgentChute service](agentchute.md)
provides cloud features when configured; its guide explains the data sent.
You can also [write custom rules](custom-rules.md) for repository-specific needs.

<div class="agentlint-boundary" markdown="1">

AgentLint is a rule and heuristic layer. It can miss behavior, flag legitimate
actions, and be bypassed by a process with broad access. Keep code review, tests,
CI, and least-privilege credentials in place. Use [diagnostics](diagnostics.md)
and [narrow configuration adjustments](configuration.md) when a finding needs
investigation.

</div>

## Using AgentLint

- [Rules](rules.md) — every rule, by pack, with options
- [Configuration](configuration.md) — project policy, paths, and exceptions
- [Approvals and evidence](approvals-and-evidence.md) — time-boxed approvals and verification receipts
- [Diagnostics](diagnostics.md) — observation, troubleshooting, and patch previews
- [CI](ci.md) — checks on pull requests
- [MCP server](mcp.md) — content and patch checks from MCP clients
- [AgentChute](agentchute.md) — optional cloud features and privacy
- [CLI reference](cli.md) — commands and options

## Extending AgentLint

- [Custom rules](custom-rules.md)
- [Custom adapters](custom-adapters.md)
- [Subagent safety](subagent-safety.md)
- [Architecture](architecture.md)

## Read more

- [Catch risky AI coding actions before they reach your repository](https://medium.com/@mauricio_perez_r/catch-risky-ai-coding-actions-before-they-reach-your-repository-92ac1197ee31) — AgentLint's action and feedback loop.
- [Your coding agent needs a stopping rule](https://medium.com/@mauricio_perez_r/your-coding-agent-needs-a-stopping-rule-330bffdea890) — completion contracts and bounded repairs with ConstraintLoop.
- [Your AI agent says it's done. What proves it?](https://medium.com/@mauricio_perez_r/your-ai-agent-says-its-done-what-proves-it-cd945ac8c68e) — following evidence through review, delivery, and acceptance.

[Source and issues on GitHub](https://github.com/mauhpr/agentlint) ·
[Releases](https://github.com/mauhpr/agentlint/releases) ·
[Changelog](https://github.com/mauhpr/agentlint/blob/main/CHANGELOG.md)
