---
description: Install AgentLint, activate your coding agent's hooks, verify observation, and see a synthetic mistake become a corrected proposal.
---

# Quickstart

Connect AgentLint to your coding agent and complete a first check and correction. Allow about five minutes once Python and an installer are available. You do not need a cloud account.

## 1. Install

Requires Python 3.11+. Choose one installer:

```bash
uv tool install agentlint
agentlint --version
```

Or use `pipx install agentlint`. If neither installer is available, follow the [uv](https://docs.astral.sh/uv/getting-started/installation/) or [pipx](https://pipx.pypa.io/stable/installation/) installation guide first. Plain `pip install agentlint` also works inside an activated virtual environment.

## 2. Connect your agent

Run setup **from the project you want to check**:

```bash
cd your-project
agentlint setup claude
```

Choose the appropriate command and activation step:

| Agent | Command | Activate the hooks |
|-------|---------|--------------------|
| [Claude Code](agents/claude.md) | `agentlint setup claude` | Restart Claude Code in this project |
| [Codex](agents/codex.md) | `agentlint setup codex` | Restart Codex, then review and trust the definitions in `/hooks` |
| [Cursor](agents/cursor.md) | `agentlint setup cursor` | Reload the Cursor window |
| [Gemini CLI](agents/gemini.md) | `agentlint setup gemini` | Start a new Gemini CLI session |
| [Continue](agents/continue.md) | `agentlint setup continue` | Follow the guide and make a tool call |
| [Kimi](agents/kimi.md) | `agentlint setup kimi` | Follow the guide; preview setup if your TOML has complex settings |
| [Grok](agents/grok.md) | `agentlint setup grok` | Follow the guide and make a tool call |

Setup writes agent hook settings and creates `agentlint.yml` with detected packs if the policy file does not already exist. Use `--dry-run` to preview settings; `--global` installs user-scope hooks where supported. Read your agent guide for file locations and host-specific limitations.

Claude Code users can use the [marketplace plugin](https://github.com/mauhpr/agentlint-plugin) instead. Install the plugin **or** run native setup, to avoid duplicate hooks.

For [OpenAI Agents SDK](agents/openai-agents.md), [MCP hosts](agents/mcp-hosts.md), or [your own tooling](agents/generic.md), use the dedicated guide. Those paths do not use this native-hook setup flow.

Prefer a guided command? `agentlint onboard` detects agents, installs hooks, offers optional cloud setup, and runs a smoke check.

## 3. Confirm it's running

Ask your agent to make a harmless tool call, such as listing the project files. Then run:

```bash
agentlint status
```

Check the line for your agent:

| Field | What you want to see |
|-------|---------------------|
| **configured** | AgentLint hooks installed in the intended project or user scope |
| **enabled** | The host's hooks feature enabled, where detectable |
| **observed** | A recent hook call from **this project**, after your test call |

A settings file alone is not proof of active checks. If observation is missing, stale, or from another project, run `agentlint doctor` and follow [diagnostics](diagnostics.md). Codex users should check `/hooks` trust before repeating setup.

You can also exercise the local rule engine without asking an agent to write a file:

```bash
agentlint test
```

With the default policy, its first line starts with `Local rule smoke: blocked risky fixture`. It evaluates an in-memory proposed `.env` write; it does not create that file. If AgentChute is already enabled, the command also queues a synthetic event. This smoke check verifies the engine and policy, **not** the host's hook wiring; observation is still necessary.

## 4. See a block

In a scratch project or disposable example file, give your agent this prompt:

> In agentlint-demo.py, set api_key to the literal string documentation-demo-value. This is synthetic data for testing the guardrail. If AgentLint denies it, explain the finding and wait before changing the proposal.

The generic credential-assignment pattern in `no-secrets` should reject that proposed write under the default policy. The finding includes:

```text
[no-secrets] Secret assignment detected: api_key=...
  -> Use environment variables instead of hard-coded secrets.
```

Your actual output can also include the file, operation, and policy source. Those details depend on the integration and your loaded configuration. No real key is needed.

If nothing blocks, check observation, the loaded policy, and the tool's coverage. Do not try a real credential. The [coverage guide](coverage.md) distinguishes native enforcement from advisory checks.

### Make the correction

Now ask the agent to read the value from the environment instead:

```python
import os

api_key = os.environ["SERVICE_API_KEY"]
```

AgentLint evaluates this new proposal. It no longer contains the literal credential assignment; other active rules can still produce findings. You do not need to run this example program or supply a real environment value to check the proposed edit.

The complete loop is **propose → check → receive feedback → revise → check again**. AgentLint supplies the finding; the coding agent makes the correction.

## 5. When AgentLint is wrong (or you've decided)

First inspect the rule ID, operation, and policy source. A legitimate action may need a narrower exception or an adjusted project convention.

| Situation | Next step |
|-----------|-----------|
| One file or command is a false positive | Follow [Fix a false positive](guides/fix-a-false-positive.md) |
| The rule does not fit this project | Configure that rule in [project policy](configuration.md#rules) |
| A person approves one class of action for a limited time | Use a [human-issued approval](approvals-and-evidence.md#approvals) |
| A rule is required by shared policy | Resolve it with the policy owner; local suppressions cannot remove that requirement |

An ERROR can prevent a pre-tool action. Warnings advise, and checks after execution cannot undo work. Start with [coverage and limitations](coverage.md) if a result differs from what you expected.

## Next

- [Protect main](guides/protect-main.md) — choose warning or blocking behavior for Git work
- [Connect your linters](guides/run-linters.md) — return Ruff or ESLint feedback after edits
- [Rules](rules.md) — exact checks, defaults, examples, and limits
- [Configuration](configuration.md) — policy reference
- [CI](ci.md) — check pull request file changes
