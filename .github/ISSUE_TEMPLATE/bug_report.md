---
name: Bug report
about: Report a problem with AgentLint
labels: bug
---

<!--
Security vulnerabilities (for example a bypass of an ERROR rule or a credential
leak): do not open a public issue. See SECURITY.md.
Redact secrets, tokens and private paths from everything you paste below.
-->

## What happened

A clear description of the problem.

## Command or tool call

The exact command, file write or tool call that AgentLint blocked or allowed:

```text

```

## Expected behaviour

What you expected AgentLint to do (block, allow, warn) and why.

## Actual behaviour

What AgentLint did. Include the message shown to the agent and any error output.

## Steps to reproduce

1.
2.
3.

## Environment

- Coding agent and version (e.g. Claude Code 2.x, Cursor, Codex CLI):
- OS:
- Python version:
- `agentlint --version`:
- Install method (uv tool, pipx, pip, Claude Code plugin):

<details>
<summary><code>agentlint status --json</code> (redact paths)</summary>

```json

```

</details>

## Diagnostic bundle (optional)

A sanitized record of the hook call helps most. If you have the hook input as
JSON, pipe it to `agentlint check` with `--diagnostic-bundle`:

```bash
agentlint check --event PreToolUse --adapter claude \
  --diagnostic-bundle agentlint-bundle.json < hook-input.json
```

Review the file, then attach it. See `docs/diagnostics.md`.

## Configuration (optional)

Relevant parts of `agentlint.yml`, if any.
