# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 2.9.x   | Yes       |
| < 2.9   | No        |

Security fixes are released as patch versions of the latest minor release.
Upgrade with `agentlint update`.

## Reporting a vulnerability

**Do not open a public GitHub issue.**

Use GitHub private vulnerability reporting (the repository's **Security** tab →
**Report a vulnerability**), or email **mauricio_perez_r@hotmail.com** with the
subject prefix `[SECURITY][AgentLint]`. Include:

- a description of the vulnerability;
- steps to reproduce, including the agent, the exact tool call or command, and
  your AgentLint version (`agentlint --version`);
- the impact you expect.

Do not include real credentials in the report. Redact paths and secrets.

## Response timeline

- **Acknowledgment**: within 48 hours.
- **Initial assessment**: within 1 week.
- **Fix or mitigation**: as soon as practical, depending on severity.

We will coordinate disclosure with you and credit you in the release notes
unless you prefer otherwise.

## Scope

AgentLint is a guardrail that inspects tool calls from AI coding agents through
their hook systems. Examples of what we treat as vulnerabilities:

- **Bypass of an ERROR rule**: a command or file write that an ERROR rule is
  documented to block, but which AgentLint allows (for example through quoting,
  shell parsing, path handling, or an adapter's payload shape).
- **Bypass of required rules or approvals**: disabling or exempting a required
  workspace rule or locked organization rule, or an agent creating or widening
  an approval.
- **Credential leakage**: secrets or file contents written to logs, session
  state, local recordings, diagnostic bundles, or AgentChute events beyond the
  documented privacy-safe summaries.
- **Code execution from hook input**: a hook payload, config file or hook file
  that makes AgentLint execute code or commands it should not.
- **Unsafe hook installation**: `setup`, `onboard` or `doctor --fix` writing
  hook or config files that weaken the agent's existing security settings.

## What AgentLint is not

AgentLint is not a sandbox. It only sees what the agent sends to its hooks, and
it cannot stop actions that never pass through a hook: commands the agent's
platform does not report, programs that a permitted command starts, or agents
running without hooks installed. Rules are pattern- and parser-based and can be
evaded; treat AgentLint as one layer alongside OS permissions, scoped
credentials, branch protection and review. Missed detections that are not a
documented guarantee are bugs, not vulnerabilities; report them as normal
issues.

The `security` pack is opt-in because its rules are stricter and may produce
false positives (for example, build scripts that write files through the
shell). Enable it with:

```yaml
packs:
  - security
```

See [docs/rules.md](docs/rules.md) for what each rule covers.
