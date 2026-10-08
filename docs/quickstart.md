# Quickstart

Install AgentLint, connect it to your coding agent, confirm it's running, and
see what happens when it blocks something. About five minutes.

## 1. Install

AgentLint needs Python 3.11+.

```bash
pipx install agentlint        # or: uv tool install agentlint / pip install agentlint
agentlint --version
```

## 2. Connect your agent

From your project directory:

```bash
agentlint setup claude        # or: cursor, codex, gemini, continue, kimi, grok
```

This adds AgentLint hooks to the agent's project settings and creates
`agentlint.yml` with packs detected from your project. Hooks call AgentLint by
absolute path, so they work however you installed it. Add `--global` to install
for all projects instead (where the agent supports it).

`agentlint onboard` is the guided version: it detects the agents you use,
installs hooks, can update AgentLint and connect the optional
[AgentChute](agentchute.md) service, and runs a smoke test.

For OpenAI Agents SDK, MCP hosts or your own tooling, see
[Agents](README.md#agents).

## 3. Confirm it's running

Restart the agent (and, for Codex, approve the new hooks in `/hooks`), make any
tool call, then run:

```bash
agentlint status
```

Each agent shows three things:

- **configured** — the hook file exists (project or user scope);
- **enabled** — the agent's hooks feature is on, where AgentLint can check;
- **observed** — when AgentLint last received a hook call from that agent.

"never observed" after a tool call means the hook isn't reaching AgentLint; see
[Diagnostics](diagnostics.md).

## 4. See a block

Ask your agent to write a fake live key into a file, for example
`STRIPE_KEY = "sk_live_abc123def456ghi789"` in `config.py`. The write is
refused before it happens, and the agent receives:

```text
[no-secrets] Possible secret token detected (prefix 'sk_live_')
  File: /path/to/project/config.py
  Operation: Write
  Policy: built-in universal pack; built-in defaults (no policy file)
  -> Use environment variables instead of hard-coded secrets.
```

Every finding names the rule, the file or command, which policy made the rule
active, and what to do instead. Warnings look the same but don't stop the
action.

## 5. When AgentLint is wrong (or you've decided)

Pick the narrowest tool:

| Situation | Do this |
|-----------|---------|
| A rule doesn't fit this project | `rules: {<rule>: {enabled: false}}` in `agentlint.yml` |
| A rule is wrong for some files | `allow_paths` or `# agentlint:ignore <rule> reason="..."` |
| One reviewed command must run | An [exception](configuration.md#exceptions) (≤ 7 days) |
| You approve a kind of action for now | `agentlint approve grant <class> --reason ...` ([approvals](approvals-and-evidence.md)) |
| A warning repeats and you've seen it | `agentlint suppress <rule>` for the session |

## Next

- [Rules](rules.md) — what's checked, by pack
- [Configuration](configuration.md) — `agentlint.yml` reference
- [CI](ci.md) — the same checks on pull requests
- [Diagnostics](diagnostics.md) — `status`, `doctor`, previews and troubleshooting
