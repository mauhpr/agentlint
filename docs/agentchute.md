# AgentChute (optional cloud)

AgentLint works fully offline. AgentChute is an optional hosted service that
adds two things for teams:

- **Threat feeds** — curated lists (compromised packages, GHSA and NVD
  vulnerabilities, leaked-secret patterns, malicious URLs and domains,
  compromised GitHub Actions) that power the [cloud-feed rules](rules.md).
  Without AgentChute those rules do nothing; every other rule still runs.
- **Team visibility and policy** — a dashboard of privacy-safe event summaries,
  and an organization policy that is cached locally and enforced on every
  machine (organization rules can't be disabled or excepted locally).

Nothing is sent unless you opt in with a team key.

## Enable

```bash
agentlint login                      # pair this machine through the dashboard
# or
agentlint init --team-key=ac_team_...
```

`init --team-key` enables AgentChute in `agentlint.yml` and prints the
environment variables to add to your shell, CI or agent settings; the key itself
is not written to the repository. `agentlint env install|remove|show|doctor`
manages a shell profile block for you.

```bash
export AGENTCHUTE_LICENSE_KEY=ac_team_...
export AGENTCHUTE_ENABLED=true
# export AGENTCHUTE_API_URL=...      # self-hosted API
```

Restart the coding agent after changing its environment.

## What is sent

Hooks never wait on the network. Each check appends a summary to a local queue,
and a short background process uploads it later. A summary contains:

- the event, tool name, rule IDs and severities, and whether the action was blocked;
- for shell commands, only the executable and a known subcommand
  (`git push [arguments redacted]`);
- for file edits, the file type (`[path .py]`) and content lengths — never paths
  or contents;
- prompts, searches, URLs and task descriptions only as redacted lengths;
- a hash of the project path, the agent platform and the AgentLint version.

Review queued summaries with `agentlint queue inspect`.

## When the cloud is unavailable

Protection doesn't depend on connectivity. `agentlint status` and
`agentlint doctor` show whether delivery is healthy or degraded (rate limiting,
server errors, failing credentials), how many events are waiting and how old the
oldest one is, when the next retry happens, and what is still enforced locally:
all pack rules, required workspace rules and the last cached organization
policy.

Rate-limited uploads respect the server's `Retry-After`. Events are never
discarded automatically; a backlog over 10,000 events or 50 MB is reported.

| Command | Purpose |
|---------|---------|
| `agentlint queue status` | Queue size, backlog age and retry state |
| `agentlint queue inspect` | Show queued summaries |
| `agentlint sync` / `agentlint queue flush` | Upload now |
| `agentlint queue discard-pending` | Mark the backlog delivered without sending it |
| `agentlint policy status` | Cached organization policy; `--online` tests the connection |
| `agentlint policy explain` | Which cached rules are enforced and where they came from |
| `agentlint policy refresh` | Fetch the latest policy |

If you disconnect AgentChute, leftover queued events stay on disk and are not
sent; `status` reports them so you can discard them.

## Turning it off

Remove `agentchute: enabled: true` from `agentlint.yml` and unset
`AGENTCHUTE_ENABLED` / `AGENTCHUTE_LICENSE_KEY` (`agentlint env remove`).
