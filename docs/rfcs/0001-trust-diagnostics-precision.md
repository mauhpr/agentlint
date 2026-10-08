# RFC 0001 — Trust, Diagnostics and Precision (v2.8.0, v2.9.0)

Status: Accepted · Target: 2.8.0 (A–D), 2.9.0 (E–H)

## Problem

Field feedback from Codex sessions on 2.7.1 found the rules themselves correct,
but operators could not tell **whether they were protected, why an action was
denied, or what change would be accepted**:

- `status` only inspects project-local hook files, so user-scope installs
  (`~/.codex/hooks.json`) report `missing`, and `doctor --fix` then installs a
  second, unscoped integration. Nothing records that hooks actually ran.
- The AgentChute queue treats HTTP 429 like any failure, ignores `Retry-After`,
  and reports no backlog age. `doctor` refreshes the policy cache as a side
  effect and does not say which protections still run locally.
- `apply_patch` inspection raises one message for missing and ambiguous hunks,
  without the file, hunk number, repeated context or candidate lines. There is
  no way to preview a patch against the validator.
- `policy_source` cannot distinguish built-in defaults, workspace policy and
  repository policy.
- Shell rules match raw text: quoted arguments to read-only commands and
  heredoc bodies look like mutations, and `allow_patterns` exempts the whole
  command string, including unrelated chained operations.
- Explicit `packs:` silently replaces stack detection, so a config written for
  an earlier repository shape drifts unnoticed.
- Session approval lists are read by rules but never written, and nothing
  separates approval classes.
- Test evidence is a substring heuristic (`echo pytest` counts as a test run).

## Principles

1. Never weaker than today: every new parser path falls back to the existing
   raw-text behaviour when it cannot fully understand the input.
2. Diagnostics are read-only. `status`, `doctor` (without `--fix`/`--online`)
   and previews do not write policy caches, sessions, recordings or queues.
3. Locked, required and organization rules are never relaxed by approvals,
   receipts, exceptions or structured allowances.
4. No product- or company-specific integrations upstream; external tools
   integrate through documented file formats.

## 2.8.0 — Coverage truth and actionable diagnostics

**A. Coverage.** Hook inspection moves to `agentlint.coverage`. Each platform is
checked at project and user scope (paths taken from the adapters), the hook
JSON is parsed for wired events, and wrapper commands that delegate to AgentLint
are reported as `wrapper` rather than `missing`. `check` writes a small
heartbeat (`~/.cache/agentlint/heartbeat/<platform>.json`: event, tool,
project hash, version, timestamp — no content). `status` reports three tiers:
*configured*, *enabled* (where knowable, e.g. Codex `config.toml`) and
*observed* (heartbeat age). `doctor --fix` does not add project hooks when a
user-scope installation already covers the platform.

**Effective policy.** Config loading records layers
(`builtin` / `workspace` / `repository`) and which layer last set each rule.
`status` prints them, plus the workspace variable, required rules and exception
count. `status --json` exposes the same data.

**B. Degraded cloud operation.** The event client classifies responses
(`ok`, `rate_limited`, `server_error`, `auth_error`, `network_error`) and parses
`Retry-After` (seconds or HTTP date, capped at one hour). The retry file records
the last status and success. `queue_status` adds oldest pending age, bytes and
soft-cap warnings; nothing is discarded automatically. `doctor` is read-only by
default and prints a Cloud section listing what is still enforced locally.

**C. Patch diagnostics.** `PatchError` carries `path`, `hunk`, `reason`
(`missing`/`ambiguous`/`anchor-missing`/`syntax`), a redacted, truncated
context excerpt and candidate line numbers. `@@` anchors keep Codex's
first-match-after-cursor semantics. `agentlint check-patch`
(and MCP `check_patch`) runs the identical inspection and rule evaluation with a
throwaway session.

**D. Actionable denials.** Violations show `File: path:line`, operation, a
policy source naming the layer, and a correction.

## 2.9.0 — Precision, drift, approvals and evidence

**E. Parsed operations.** `split_operations()` segments simple command lists on
`&&`, `||`, `;` and `|` and classifies each segment as display, read, mutate or
unknown. Mutation rules see only the non-data segments; any unsupported syntax
returns `None` and the raw command is used. New `allow_operations` entries are
matched per segment, so an allowance cannot exempt another chained operation.

**F. Drift.** `detect_drift()` compares explicit packs with detected stack
signals and reports omissions in `status` and `doctor`. Config is never changed.

**G. Typed approvals.** See ADR 0002.

**H. Evidence receipts.** See ADR 0003.
