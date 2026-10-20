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
| `fixture-copy` | `no-bash-file-write`, only for an exact, hash-bound fixture copy |

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

### Bounded fixture copies

A person can approve a retained fixture without allowing arbitrary shell writes:

```bash
agentlint approve grant fixture-copy --project-dir /abs/repo --ttl 30m \
  --reason "Retained HTML for the parser regression" \
  --operation "cp /abs/repo/retained.html /abs/repo/tests/fixtures/page.html"
```

Both paths must be absolute and resolve inside that worktree. The destination
must be in `fixtures/` or `testdata/`, its parent must already exist, and the
source must be a regular file no larger than 5 MB. Direct symlinks, recursive
copies, flags, compound commands, and overwriting different content are rejected.
The source SHA-256 and resolved paths are bound to the approval and included in
each use's audit record. A changed source or retargeted path no longer matches.
The same approved operation can be reused until expiry or revocation, including
an idempotent copy over identical content. Other rules still apply.

This is an audited hook check, not an atomic filesystem transaction: it does not
prevent a concurrent process changing a file after inspection. Use the OS sandbox
and repository review for those boundaries.

Existing grants remain active across hook invocations. Check `agentlint approve
list` before requesting a new grant. Chat acknowledgments and OS tool approvals
are separate from AgentLint grants; AgentLint does not infer or create them.

## Evidence

AgentLint records **receipts**: small JSON files saying what was verified, in
which repository, at which commit.

When an agent finishes a recognized test command — `pytest`, `python -m pytest`,
`uv run pytest`, `make test`, `npm`/`pnpm`/`yarn test`, `vitest`, `jest`,
`go test`, `cargo test` — AgentLint writes a `test-run` receipt. Redirected runs
(`uv run pytest -q > log 2>&1`, `| tee log`) count. `echo pytest` does not, and
a run the agent reports as failed doesn't produce a receipt. Some agents don't
report exit codes; those receipts say "completed, result not reported".

`drift-detector` uses receipts: a fresh one for the current commit, worktree and
session, newer than the last edit, satisfies "run the tests before committing".
Its warnings cite only evidence in that scope. Sessionless external receipts
remain visible through `agentlint evidence` but do not satisfy the drift check.
Absolute-path edits are attributed to the file's actual Git worktree, even when
the selected project is a parent directory. Saving evidence or other non-code
files does not advance the last code-edit timestamp.

### Local logs and JSON evidence

The file-write guard already permits scratch log destinations:

```bash
uv run pytest -q 2>&1 | tee /private/tmp/test-evidence.log
```

A standalone `cat <<'EOF'` with one quoted delimiter is stdin data, not a
file write. `python3 - <<'PY'` uses the Python syntax checker for its literal
body. Shell operations after the closing delimiter, unknown interpreter syntax,
writes and opaque Python operations do not gain a read-only exemption.

For a project-local evidence directory, configure narrow `no-bash-file-write`
`allow_paths` globs rather than disabling the rule or whitelisting an entire
compound command. Other guards continue to evaluate the command. Valid `.json`
data is exempt from `max-file-size` by default, so pretty-printing a receipt
does not trigger a code-module line limit. Set `exempt_json_data: false` under
that rule to retain line-count checks on JSON. Content/security checks still run.

With `cli-integration.diff_only: true`, only located findings on changed lines
are retained. When all such findings are removed, their summary no longer emits
a warning by itself. Unlocated tool failures remain visible. The configured
linter interprets its suppression comments, including `# noqa: F401`; AgentLint
does not strip these comments or override the linter's suppression policy.
Both stdout and stderr are retained. Tool/configuration errors are not treated
as source diagnostics merely because their messages contain a line number.

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
| `session_id` | Session key; required for reuse by `drift-detector`, optional for evidence display |

AgentLint's own receipts live in `~/.cache/agentlint/receipts`
(`AGENTLINT_RECEIPTS_DIR`).
