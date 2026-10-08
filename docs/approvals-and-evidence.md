# Approvals and evidence

Two ways to tell AgentLint what a person has decided and what has been
verified, without turning rules off.

## Approvals

An approval lets a person allow one **class of action** in one repository for a
limited time. While it's active, rules in that class report a warning that cites
the approval instead of blocking.

```bash
agentlint approve grant git-push-protected --reason "hotfix 4.2.1" --ttl 30m
agentlint approve grant destructive-op --reason "reset sandbox DB" \
  --operation "dropdb sandbox"            # only this exact command
agentlint approve list
agentlint approve revoke apr_1a2b3c4d
```

| Class | Rules it covers |
|-------|-----------------|
| `git-push-protected` | `no-push-to-main`, `no-force-push` |
| `git-merge` | Merging into a protected branch (reserved; no built-in rule yet) |
| `infra-apply` | `dry-run-required`, `cloud-infra-mutation` |
| `cloud-delete` | `cloud-resource-deletion` |
| `cloud-paid-create` | `cloud-paid-resource-creation` |
| `destructive-op` | `destructive-confirmation-gate`, `no-destructive-commands` |
| `cicd-edit` | `cicd-pipeline-guard` |
| `package-publish` | `package-publish-guard` |
| `production-access` | `production-guard` |
| `model-spend` | `token-budget`, `token-burn-against-team-budget` |

How approvals are scoped:

- **One class only.** An approval never covers another class: "the PR is
  merged" (`git-merge`) does not approve spending (`model-spend`).
- **One repository**, and optionally one exact command (`--operation`).
- **Expiring.** `--ttl` defaults to `1h`; the maximum is `24h`.
- **Audited.** Each use is logged to `~/.cache/agentlint/approval-audit.jsonl`
  before the rule is relaxed; if logging fails, the rule still blocks.
- **Never for required or organization rules.**
- **People only.** `grant` requires an interactive terminal and confirmation.
  If an agent tries to run `agentlint approve grant` or edit the approvals file,
  the call is blocked (`approval-self-grant`).

For a single reviewed command in configuration, see
[exceptions](configuration.md#exceptions).

## Evidence

AgentLint records **receipts**: small JSON files saying what was verified, in
which repository, at which commit.

When an agent finishes a recognized test command — `pytest`, `python -m pytest`,
`uv run pytest`, `make test`, `npm`/`pnpm`/`yarn test`, `vitest`, `jest`,
`go test`, `cargo test` — AgentLint writes a `test-run` receipt. Redirected runs
(`uv run pytest -q > log 2>&1`, `| tee log`) count. `echo pytest` does not, and
a run the agent reports as failed doesn't produce a receipt. Some agents don't
report exit codes; those receipts say "completed, result not reported".

`drift-detector` uses receipts: a fresh one for the current commit, newer than
the last edit, satisfies "run the tests before committing", and its warnings
say what the latest evidence is.

```bash
agentlint evidence            # latest local tests, review, verified deploy
agentlint evidence --json
```

Evidence never unblocks an ERROR.

### Receipts from other tools

Any tool can contribute receipts. Write one JSON object per file into a
directory and list it in `agentlint.yml`:

```yaml
evidence:
  receipts_dirs: [~/.local/state/my-tool/receipts]
  max_age: 24h          # default
```

```json
{
  "v": 1,
  "kind": "deploy-verified",
  "command": "smoke-test production",
  "exit_code": 0,
  "repo": "/abs/path/to/repo",
  "git_sha": "3f1c9e0...",
  "created_at": "2026-10-08T16:00:00+00:00",
  "producer": "my-tool"
}
```

| Field | Meaning |
|-------|---------|
| `kind` | `test-run`, `review` or `deploy-verified` |
| `exit_code` | `0` for success; `null` if unknown; non-zero receipts are ignored |
| `repo` | Absolute repository path, matched exactly |
| `git_sha` | Optional; if present it must equal the repository's current `HEAD` |
| `created_at` | ISO 8601 with time zone; older than `max_age` is ignored |

AgentLint's own receipts live in `~/.cache/agentlint/receipts`
(`AGENTLINT_RECEIPTS_DIR`).
