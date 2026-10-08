# ADR 0003 — Evidence receipts

Status: Accepted · Release: 2.9.0

## Context

Findings need to cite what has actually been verified. Test detection was a
substring heuristic (`echo pytest` counted as a test run; a completed
`uv run pytest -q > log 2>&1` gave no evidence of passing), and external tools
that already record verification could not share it with AgentLint.

## Decision

A receipt is one JSON object per file (`*.json`) in a receipts directory:

```json
{
  "v": 1,
  "kind": "test-run",
  "command": "uv run pytest -q",
  "exit_code": 0,
  "repo": "/abs/path/to/repo",
  "git_sha": "abc123...",
  "created_at": "2026-10-08T16:00:00Z",
  "producer": "agentlint"
}
```

`kind` is one of `test-run`, `review`, `deploy-verified`. `git_sha` is
optional; when present it must match `HEAD` for the receipt to count.

- AgentLint writes `test-run` receipts itself on PostToolUse when a parsed
  operation is a recognized test runner (pytest, `python -m pytest`,
  `uv run pytest`, `make test`, npm/pnpm/yarn test, vitest, jest, go test,
  cargo test), including runs whose output is redirected (`> log 2>&1`,
  `| tee log`). If the hook payload reports a non-zero exit status the run does
  not count; if it reports none, the receipt records `exit_code: null`
  ("completed, result unknown").
- Configuration: `evidence.receipts_dirs` (extra directories written by other
  tools) and `evidence.max_age` (default `24h`). AgentLint's own directory is
  `~/.cache/agentlint/receipts` (`AGENTLINT_RECEIPTS_DIR`).
- Consumers: `drift-detector` treats a fresh passing (or completed) test
  receipt newer than the last edit as satisfying "tests run since edits".
  Findings and `agentlint evidence` cite the evidence level:
  local tests, reviewed, or verified deployment.
- Receipts are advisory evidence only. They never unblock an ERROR.

## Consequences

Any tool can integrate by writing receipts; no tool-specific code is needed in
AgentLint.
