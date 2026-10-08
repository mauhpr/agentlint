# ADR 0002 — Typed, expiring approvals

Status: Accepted · Release: 2.9.0

## Context

A human approval for one kind of action (for example, "the PR is merged, go
ahead") was being read by agents as permission for unrelated actions such as
model spending. AgentLint rules read untyped session lists
(`confirmed_destructive_ops`, `confirmed_cloud_deletions`, `approved_cicd_files`)
that no supported interface writes, and the 2.7.0 `exceptions:` are per rule
and exact command only.

## Decision

- Approvals are **typed by action class**: `git-push-protected`, `git-merge`,
  `infra-apply`, `cloud-delete`, `cloud-paid-create`, `destructive-op`,
  `cicd-edit`, `package-publish`, `production-access`, `model-spend`.
  Each built-in rule that can require approval declares one class. A grant for
  one class never satisfies a rule of another class.
- Grants are created by a human with
  `agentlint approve grant <class> --reason ... [--ttl 1h] [--operation "<cmd>"]`
  in an interactive terminal. TTL defaults to one hour, maximum 24 hours. A
  grant is bound to one repository (absolute path) and, optionally, to one
  exact literal command.
- Agents cannot self-approve: the CLI refuses without a TTY, and the hook
  blocks any agent tool call that runs `agentlint approve grant` or writes the
  approvals file.
- A matching grant turns that rule's ERROR into a WARNING that cites the grant;
  every use is audited (`~/.cache/agentlint/approval-audit.jsonl`). Grants never
  apply to locked, required-workspace or organization (AgentChute) rules.
- Storage: `~/.cache/agentlint/approvals.jsonl` (`AGENTLINT_APPROVALS_FILE`),
  owner-only permissions. `approve list` / `approve revoke <id>` manage it.

## Consequences

Approval scope is explicit and expires. "PR merged" can be expressed as a
`git-merge` grant without implying `model-spend`. The legacy session lists keep
working but are no longer documented.
