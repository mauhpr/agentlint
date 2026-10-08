# AgentLint

[![CI](https://github.com/mauhpr/agentlint/actions/workflows/ci.yml/badge.svg)](https://github.com/mauhpr/agentlint/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/mauhpr/agentlint/branch/main/graph/badge.svg)](https://codecov.io/gh/mauhpr/agentlint)
[![PyPI](https://img.shields.io/pypi/v/agentlint)](https://pypi.org/project/agentlint/)
[![Python](https://img.shields.io/pypi/pyversions/agentlint)](https://pypi.org/project/agentlint/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Guardrails for AI coding agents.** AgentLint checks what your agent is about
to do — every file write, edit and shell command — and stops the dangerous
parts before they happen: hard-coded secrets, force-pushes to `main`,
destructive commands, edits to CI pipelines, risky cloud operations.

It works with **Claude Code, Codex, Cursor, Gemini CLI, Continue, Kimi, Grok**,
the **OpenAI Agents SDK**, **MCP** hosts and your own tools. It runs locally,
and nothing leaves your machine unless you opt in.

## Install

```bash
pipx install agentlint            # Python 3.11+; or: uv tool install agentlint
cd your-project
agentlint setup claude            # or: codex, cursor, gemini, continue, kimi, grok
```

`setup` adds AgentLint hooks to the agent's settings and writes an
`agentlint.yml` with packs detected from your project. Restart the agent, make
any tool call, and check that it's working:

```bash
agentlint status
```

```text
Coding agents (configured -> enabled -> observed):
  ✓ claude   (detected) configured: installed (project: …/.claude/settings.json) [PreToolUse, PostToolUse, …] | observed: 4s ago (PreToolUse, this project)
```

Full walkthrough: **[Quickstart](docs/quickstart.md)**.

## What a block looks like

When an agent tries to write a live API key into `config.py`, the write never
happens. The agent is told why and what to do instead:

```text
[no-secrets] Possible secret token detected (prefix 'sk_live_')
  File: /path/to/project/config.py
  Operation: Write
  Policy: built-in universal pack; built-in defaults (no policy file)
  -> Use environment variables instead of hard-coded secrets.
```

Findings come in three levels:

- **ERROR** blocks the action;
- **WARNING** is passed to the agent as advice;
- **INFO** appears in the end-of-session report.

## What it checks

77 rules in 8 packs. `universal` and `quality` are always on; language packs
turn on when AgentLint detects them; `security` and `autopilot` are opt-in.

| Pack | Rules | Examples |
|------|-------|----------|
| universal | 24 | secrets, `.env` writes, force-push, destructive commands, CI/CD edits, package publishing, test weakening |
| quality | 7 | oversized diffs, removed error handling, dead imports, commit message format |
| python | 6 | SQL built with f-strings, unsafe shell calls, bare `except`, risky migrations |
| frontend | 8 | missing alt text and labels, focus styles, touch targets |
| react | 3 | unhandled loading/error states, empty states |
| seo | 4 | page metadata, Open Graph, semantic HTML |
| security | 7 | file writes and data exfiltration through the shell |
| autopilot | 18 | production targets, cloud deletions, IAM/firewall changes, `terraform apply` without a plan *(experimental)* |

Every rule and option: **[Rules](docs/rules.md)**.

## Configure

```yaml
# agentlint.yml
packs: [python, security]      # added to universal + quality
rules:
  max-file-size:
    limit: 400
  no-todo-left:
    enabled: false
```

When a rule gets in the way, use the narrowest fix:

| Situation | Do this |
|-----------|---------|
| The rule doesn't fit this project | `enabled: false` in `agentlint.yml` |
| The rule is wrong for some files | `allow_paths`, or `# agentlint:ignore <rule> reason="..."` |
| One reviewed command needs to run | an [exception](docs/configuration.md#exceptions) (up to 7 days) |
| You approve a kind of action, for now | `agentlint approve grant <class> --reason "..."` ([approvals](docs/approvals-and-evidence.md)) |

Shared policies for many repositories, monorepos and required rules:
**[Configuration](docs/configuration.md)**.

## Day-to-day commands

```bash
agentlint status              # is it running? which policy applies? (--json)
agentlint doctor              # find misconfiguration (read-only; --fix to repair)
agentlint check-patch x.patch # preview a Codex patch against the same checks
agentlint evidence            # latest test / review / deploy evidence for this repo
agentlint ci --diff origin/main...HEAD   # same checks in CI
agentlint uninstall claude    # remove the hooks
```

All commands: **[CLI reference](docs/cli.md)**.

## More

- [Agent setup guides](docs/README.md#agents) — one page per agent
- [CI](docs/ci.md) · [MCP server](docs/mcp.md) · [Diagnostics](docs/diagnostics.md)
- [Custom rules](docs/custom-rules.md) — write your own in a few lines of Python
- [AgentChute](docs/agentchute.md) — optional cloud: threat feeds, team policy, dashboard
- [Claude Code marketplace plugin](https://github.com/mauhpr/agentlint-plugin)

## FAQ

**Will it slow my agent down?**
Each check runs locally in a short-lived process with no network calls on the
hook path.

**Is my code sent anywhere?**
No. The optional AgentChute integration sends only redacted event summaries —
never file contents, paths, full commands or prompts — and only after you opt
in. See [what is sent](docs/agentchute.md#what-is-sent).

**Is this a sandbox?**
No. AgentLint inspects tool calls with rules and heuristics. It catches common
mistakes and risky patterns, but a determined process can get around it. Use it
alongside code review, CI and least-privilege credentials.

**A rule fires repeatedly on something legitimate.**
Please [open an issue](https://github.com/mauhpr/agentlint/issues) with the
command or diff. Meanwhile, the circuit breaker gradually downgrades a
repeatedly firing rule so it can't stall a session (except security-critical and
required rules).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Security reports: [SECURITY.md](SECURITY.md).

## License

MIT
