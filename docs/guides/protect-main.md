---
description: Understand AgentLint's Git defaults, block direct pushes with strict mode, and keep normal feature-branch work moving.
---

# Protect main without blocking normal Git work

AgentLint can check an agent's proposed Git command before it runs. Start with the built-in defaults, then decide whether your project also needs to block direct pushes.
You need a working [native hook integration](../README.md#agents); MCP checks alone are advisory.

## Understand the defaults

The `universal` pack includes both Git rules. With `severity: standard` and no approval or exemption:

| Proposed operation | Finding | Result before execution |
|---|---|---|
| Force-push with `--force` or `-f` explicitly targeting `main` or `master` | `no-force-push`, ERROR | Blocked |
| Push directly to `main` or `master` without force | `no-push-to-main`, WARNING | Agent receives advice; command proceeds |
| Force-push with `--force-with-lease` to `main` or `master` | `no-force-push`, WARNING | Agent receives advice; command proceeds |
| Push a feature branch without force | Neither Git rule fires | Other applicable rules still run |

These rules inspect command patterns. They do not query your Git host's branch protection or determine the destination of every implicit refspec.
Keep server-side branch protection enabled for the final enforcement boundary.

## Block direct pushes too

Set strict mode in the project's existing `agentlint.yml`:

```yaml
severity: strict
```

Strict mode promotes warnings to errors, including direct pushes and protected-branch pushes with lease.
It applies to all ordinary rules in the project, so review other warnings before enabling it.
Required workspace and organization rules retain their own policy severity.

Check the effective configuration:

```bash
agentlint status
agentlint doctor
```

The next hook call reads the configuration. You do not need to reinstall hooks for this change.

## Keep work on a feature branch

A normal workflow is still available:

```bash
git switch -c fix/loading-state
git push -u origin fix/loading-state
gh pr create --base main
```

The feature-branch push is not a direct push to `main` merely because a later pull request command names `main` as its base.
AgentLint checks supported compound commands operation by operation; unsupported shell syntax receives conservative raw-text checks.
See [shell command interpretation](../configuration.md#shell-commands).

## Handle an exceptional push deliberately

For a reviewed maintenance operation, a person can issue a short-lived [approval](../approvals-and-evidence.md#approvals) from their own terminal.
An agent cannot create that approval, and an existing required workspace or organization rule cannot be relaxed by one.
Use `agentlint approve list` to check existing grants before requesting another.

If the protection must remain enabled across several repositories, make the appropriate ERROR rules [required in a workspace policy](shared-policy.md).
Required rules preserve their native severity; marking a warning rule required does not turn it into a blocker.

## Check a result without running Git

Use a framework's preflight integration or a generic JSON check to evaluate a proposed command as data; see [Generic integration](../agents/generic.md#verify).
Do not test branch protection by performing an actual force-push.

Continue with [fixing a false positive](fix-a-false-positive.md), or read the exact [`no-force-push`](../rules.md#no-force-push) and [`no-push-to-main`](../rules.md#no-push-to-main) behavior.
