# CI

`agentlint ci` runs the same file rules in CI that run during agent sessions,
using the repository's `agentlint.yml`.

```bash
agentlint ci                              # staged, unstaged and untracked changes
agentlint ci --diff origin/main...HEAD    # a pull request's changes
agentlint ci --format json
```

It exits `1` when there are ERROR findings and `0` otherwise. Binary files are
skipped. `agentlint ci-setup` writes a workflow for you (`--dry-run` prints it).

## GitHub Actions

```yaml
name: AgentLint
on: [pull_request]
jobs:
  agentlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: pip install agentlint
      - run: agentlint ci --diff origin/${{ github.base_ref }}...HEAD
```

## Smoke tests

- `agentlint test` runs a safe end-to-end check of the local installation (and
  AgentChute, if enabled).
- `agentlint test-policy <template>` simulates an organization-policy template
  without running anything risky. Templates: `block-company-domain`,
  `block-curl-sh`, `block-secrets-in-writes`,
  `require-approved-package-managers`, `warn-destructive-shell`.
