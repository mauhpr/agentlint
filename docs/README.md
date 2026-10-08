# AgentLint documentation

New here? Start with the **[Quickstart](quickstart.md)**.

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

## Using AgentLint

- [Rules](rules.md) — every rule, by pack, with options
- [Configuration](configuration.md) — `agentlint.yml`, workspace policy, exemptions
- [Approvals and evidence](approvals-and-evidence.md) — time-boxed human approvals; test and review receipts
- [Diagnostics](diagnostics.md) — `status`, `doctor`, patch previews, troubleshooting
- [CI](ci.md) — run the checks on pull requests
- [MCP server](mcp.md) — check content and patches from any MCP client
- [AgentChute](agentchute.md) — the optional cloud: threat feeds, team policy, privacy
- [CLI reference](cli.md) — every command and option

## Extending and internals

- [Custom rules](custom-rules.md)
- [Custom adapters](custom-adapters.md)
- [Subagent safety](subagent-safety.md) (Claude Code)
- [Architecture](architecture.md)

Release notes are in the [CHANGELOG](../CHANGELOG.md).
