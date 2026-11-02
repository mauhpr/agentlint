---
description: Understand what AgentLint can enforce, which tools each integration inspects, and where warnings, opt-in packs, and security boundaries apply.
---

# Coverage and limitations

AgentLint can prevent an action only when it receives that action before execution and the integration enforces its decision. Start with the integration you actually use, then check the rule's event, severity, and configuration.

## Choose an integration

| Integration | How checks run | Enforcement boundary |
|-------------|----------------|----------------------|
| [Claude Code](agents/claude.md) | Native hooks for matched Bash, Write, and Edit calls | Pre-tool ERROR findings deny matched calls; subagent coverage needs separate attention |
| [Codex](agents/codex.md) | Native Bash and `apply_patch` hooks | Pre-tool ERROR findings deny matched calls; patch inspection checks every touched file |
| [Cursor](agents/cursor.md) | Native tool, shell, and file hooks | Pre-execution checks can deny supported calls; after-edit feedback cannot undo an edit |
| [Gemini CLI](agents/gemini.md) | Native before/after tool hooks | Uses Gemini's event names and mapped shell/write/edit tools |
| [Continue](agents/continue.md), [Kimi](agents/kimi.md), [Grok](agents/grok.md) | Native hook adapters | Depends on the host loading the configured hooks and reporting matching tools |
| [OpenAI Agents SDK](agents/openai-agents.md) | Tool input guardrails attached in your code | Applies only to supported tools with the guardrail attached; not every hosted or built-in tool |
| [MCP hosts](agents/mcp-hosts.md) | The agent calls AgentLint's MCP tools | Advisory: connecting the server does not force the agent to call it |
| [Generic integration](agents/generic.md) | Your code submits JSON or embeds the engine | Your integration must act on the returned decision |

The agent guides list the exact event matchers, tool names, and response formats. An adapter's presence does not prove a particular host version is emitting those events. Verify the installation in your environment.

## Confirm the hooks are active

After setup, restart or reload the host, trust new hooks where required, and make one tool call. Then run:

```bash
agentlint status
agentlint doctor
```

Check **configured**, **enabled**, and a recent **observed** hook call from the selected project. Observation proves a hook reached AgentLint; it does not prove that every tool or subagent is covered. SDK and MCP integrations have their own verification steps and are not included in native-hook status.

If observation is missing or stale, use [diagnostics](diagnostics.md) before relying on protection.

## Blocking is different from feedback

| When the check runs | What an ERROR can do |
|---------------------|----------------------|
| Before a tool call | Deny the proposed action when the host honors the decision |
| After a tool call | Report the finding and ask the agent to address it; the action already happened |
| At session end | Report remaining problems; it cannot prevent earlier actions |

In standard mode, WARNING findings advise and INFO findings provide context or reporting. [Strict mode](configuration.md#severity) promotes warnings to errors; relaxed mode demotes warnings to info. Rules can emit different severities for different patterns.

For example, `no-destructive-commands` warns on many risky commands but blocks certain catastrophic patterns. `no-force-push` blocks plain force-pushes to `main`/`master`, while protected-branch `--force-with-lease` is a warning by default. Check the [rule reference](rules.md) for details.

## Know which rules are active

- `universal` and `quality` are core packs, unless deliberately excluded.
- Language and framework packs are detected from project files when stack detection is enabled. An explicit `packs:` list replaces that detection.
- `security` is opt-in and adds stricter shell and network checks.
- `autopilot` is opt-in and experimental, covering production and infrastructure patterns.
- Feed-backed rules require data from optional [AgentChute](agentchute.md). Their presence in a core pack does not make them offline detectors.

Configuration, approvals, exemptions, and the [circuit breaker](configuration.md#circuit-breaker) affect results. Required workspace rules and locked organization rules have additional restrictions; see [shared policy](guides/shared-policy.md).

## Subagents and indirect actions

Do not assume a parent agent's hook installation covers its subagents. Claude Code coverage depends on how hooks are loaded for the subagent; AgentLint's optional briefing and transcript audit are different from real-time blocking. See [subagent safety](subagent-safety.md).

A permitted shell command can start programs whose internal actions are not separate tool calls. AgentLint inspects the reported command and supported syntax; it does not monitor every system call or child process.

## Security boundary

AgentLint is a local rule and heuristic layer. It can miss behavior, flag legitimate work, and be bypassed by a process with broad access. It is not an OS sandbox, a tamper-proof policy boundary, or a replacement for branch protection, code review, tests, or scoped credentials.

Use it to catch common mistakes and communicate project policy while work is happening. Use OS permissions and platform controls for boundaries the agent must not cross even when its hooks are absent.

## What stays local

Offline checks need no account. AgentChute event delivery is opt-in and uses redacted summaries; see [exactly what is sent](agentchute.md#what-is-sent). Local recording and diagnostic bundles have their own documented behavior in [diagnostics](diagnostics.md).

Continue with the [quickstart](quickstart.md), [rule catalogue](rules.md), or [configuration reference](configuration.md).
