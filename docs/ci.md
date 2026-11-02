# CI

Use AgentLint in pull requests to check the resulting files even when a
contributor does not have agent hooks installed. `agentlint ci` uses the
repository's `agentlint.yml` and the same applicable pre- and post-file rules.

## Check locally first

From the repository root:

```bash
agentlint ci                              # staged, unstaged and untracked changes
agentlint ci --diff origin/main...HEAD    # a pull request's changes
agentlint ci --format json
```

It exits `1` when there are ERROR findings and `0` otherwise. Binary files are
skipped. `agentlint ci-setup` writes a workflow for you (`--dry-run` prints it).

Warnings remain advisory under standard severity. If you choose `severity: strict`,
warning findings become errors in CI too; see [severity modes](configuration.md#severity).

## What CI covers

Changed files are evaluated as file writes, using their current full contents.
CI can catch issues such as detected secrets and applicable source-file patterns.
It does not reconstruct the shell commands an agent ran, block an earlier action,
or replay session-end checks. Deleted or unreadable files are skipped.
Keep [native hooks](README.md#agents) for checks before a supported tool action,
and branch protection for deciding whether a pull request can merge.

## GitHub Actions

```yaml
name: AgentLint
on: [pull_request]
permissions:
  contents: read
jobs:
  agentlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: pip install agentlint==2.10.1
      - run: agentlint ci --diff origin/${{ github.base_ref }}...HEAD
```

`fetch-depth: 0` makes the base branch history available for the diff.
The package version is pinned for reproducibility; update it deliberately when
adopting a newer release. Commit `agentlint.yml` with the repository so local
hooks and CI use the same project policy.

For another provider, install the package, fetch the comparison base, and run
the same `agentlint ci --diff` command. Use `--format json` when a job needs
structured findings rather than terminal output.

## Smoke tests

- `agentlint test` runs a safe end-to-end check of the local installation (and
  AgentChute, if enabled).
- `agentlint test-policy <template>` simulates an organization-policy template
  without running anything risky. Templates: `block-company-domain`,
  `block-curl-sh`, `block-secrets-in-writes`,
  `require-approved-package-managers`, `warn-destructive-shell`.

Continue with [external linter feedback](guides/run-linters.md) or
[sharing required rules across repositories](guides/shared-policy.md).
