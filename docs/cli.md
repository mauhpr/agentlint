# CLI reference

Generated from the command definitions by `scripts/gen_docs.py`; do not edit by hand.
Run `agentlint <command> --help` for the same text in your terminal.

## Commands

- [`agentlint agentchute`](#agentlint-agentchute) — Manage AgentChute queue, policy, and cloud status.
- [`agentlint agentchute flush`](#agentlint-agentchute-flush) — Flush queued AgentChute events now.
- [`agentlint agentchute policy`](#agentlint-agentchute-policy) — Show cached AgentChute org policy.
- [`agentlint agentchute refresh`](#agentlint-agentchute-refresh) — Refresh cached AgentChute org policy.
- [`agentlint agentchute status`](#agentlint-agentchute-status) — Show local AgentChute queue and policy status.
- [`agentlint approve`](#agentlint-approve) — Typed, expiring approvals issued by a human (docs/approvals-and-evidence.md).
- [`agentlint approve grant`](#agentlint-approve-grant) — Approve one ACTION_CLASS for this repository until the TTL expires.
- [`agentlint approve list`](#agentlint-approve-list) — List active approvals.
- [`agentlint approve revoke`](#agentlint-approve-revoke) — Revoke an approval before it expires.
- [`agentlint check`](#agentlint-check) — Evaluate rules against a tool call from stdin.
- [`agentlint check-patch`](#agentlint-check-patch) — Preview an apply_patch payload against the same validator and rules as the hook.
- [`agentlint ci`](#agentlint-ci) — Scan changed files and report violations for CI pipelines.
- [`agentlint ci-setup`](#agentlint-ci-setup) — Generate CI configuration for AgentLint.
- [`agentlint doctor`](#agentlint-doctor) — Diagnose common AgentLint misconfigurations.
- [`agentlint env`](#agentlint-env) — Manage AgentChute shell environment.
- [`agentlint env doctor`](#agentlint-env-doctor) — Check whether AgentChute env vars are available in this shell/profile.
- [`agentlint env install`](#agentlint-env-install) — Persist AgentChute env vars into the shell profile.
- [`agentlint env remove`](#agentlint-env-remove) — Remove the managed AgentChute env block from the shell profile.
- [`agentlint env show`](#agentlint-env-show) — Show AgentChute env status without revealing secrets.
- [`agentlint evidence`](#agentlint-evidence) — Show verification evidence (test runs, reviews, verified deploys) for this repo.
- [`agentlint import-agents-md`](#agentlint-import-agents-md) — Import conventions from AGENTS.md into AgentLint config.
- [`agentlint init`](#agentlint-init) — Initialize AgentLint config in the project.
- [`agentlint list-rules`](#agentlint-list-rules) — List all available rules.
- [`agentlint login`](#agentlint-login) — Pair this machine with AgentChute through the dashboard.
- [`agentlint onboard`](#agentlint-onboard) — Guided setup: update, configure AgentChute, install hooks, and smoke test.
- [`agentlint policy`](#agentlint-policy) — Inspect and refresh cached AgentChute workspace policy.
- [`agentlint policy explain`](#agentlint-policy-explain) — Explain effective cached policy behavior.
- [`agentlint policy refresh`](#agentlint-policy-refresh) — Refresh cached AgentChute workspace policy.
- [`agentlint policy status`](#agentlint-policy-status) — Show local policy cache status.
- [`agentlint queue`](#agentlint-queue) — Inspect and flush the local AgentChute queue.
- [`agentlint queue discard-pending`](#agentlint-queue-discard-pending) — Mark pending AgentChute events delivered without uploading them.
- [`agentlint queue flush`](#agentlint-queue-flush) — Flush queued AgentChute events now.
- [`agentlint queue inspect`](#agentlint-queue-inspect) — Show privacy-safe queued event summaries.
- [`agentlint queue status`](#agentlint-queue-status) — Show local AgentChute queue status.
- [`agentlint recordings`](#agentlint-recordings) — Manage session recordings.
- [`agentlint recordings clear`](#agentlint-recordings-clear) — Delete recording files.
- [`agentlint recordings list`](#agentlint-recordings-list) — Show all recordings (session key, date, event count).
- [`agentlint recordings show`](#agentlint-recordings-show) — Print formatted timeline for a session.
- [`agentlint recordings stats`](#agentlint-recordings-stats) — Aggregate insights: top tools, top rules fired, patterns.
- [`agentlint report`](#agentlint-report) — Generate session summary report (for Stop event).
- [`agentlint setup`](#agentlint-setup) — Install AgentLint hooks into agent settings.
- [`agentlint setup-agent`](#agentlint-setup-agent) — Detect and add AgentLint hooks for coding agents.
- [`agentlint status`](#agentlint-status) — Show AgentLint coverage, effective policy and cloud health.
- [`agentlint suppress`](#agentlint-suppress) — Suppress a warning rule for the rest of the session.
- [`agentlint sync`](#agentlint-sync) — Sync queued AgentChute events now.
- [`agentlint test`](#agentlint-test) — Run a safe local and AgentChute end-to-end smoke test.
- [`agentlint test-policy`](#agentlint-test-policy) — Safely simulate a named org-policy template without running a risky command.
- [`agentlint uninstall`](#agentlint-uninstall) — Remove AgentLint hooks from agent settings.
- [`agentlint update`](#agentlint-update) — Update AgentLint using the detected installer.

## agentlint agentchute

```text
Usage: agentlint agentchute [OPTIONS] COMMAND [ARGS]...

  Manage AgentChute queue, policy, and cloud status.

Options:
  --help  Show this message and exit.

Commands:
  flush    Flush queued AgentChute events now.
  policy   Show cached AgentChute org policy.
  refresh  Refresh cached AgentChute org policy.
  status   Show local AgentChute queue and policy status.
```

## agentlint agentchute flush

```text
Usage: agentlint agentchute flush [OPTIONS]

  Flush queued AgentChute events now.

Options:
  --background          Bounded background flush mode
  --max-events INTEGER  Maximum queued events to send
  --batch-size INTEGER  Maximum events per API batch
  --time-budget FLOAT   Maximum seconds to spend flushing
  --dry-run             Count events without POSTing
  --help                Show this message and exit.
```

## agentlint agentchute policy

```text
Usage: agentlint agentchute policy [OPTIONS]

  Show cached AgentChute org policy.

Options:
  --format [text|json]
  --help                Show this message and exit.
```

## agentlint agentchute refresh

```text
Usage: agentlint agentchute refresh [OPTIONS]

  Refresh cached AgentChute org policy.

Options:
  --help  Show this message and exit.
```

## agentlint agentchute status

```text
Usage: agentlint agentchute status [OPTIONS]

  Show local AgentChute queue and policy status.

Options:
  --help  Show this message and exit.
```

## agentlint approve

```text
Usage: agentlint approve [OPTIONS] COMMAND [ARGS]...

  Typed, expiring approvals issued by a human (docs/approvals-and-evidence.md).

Options:
  --help  Show this message and exit.

Commands:
  grant   Approve one ACTION_CLASS for this repository until the TTL expires.
  list    List active approvals.
  revoke  Revoke an approval before it expires.
```

## agentlint approve grant

```text
Usage: agentlint approve grant [OPTIONS] ACTION_CLASS

  Approve one ACTION_CLASS for this repository until the TTL expires.

Options:
  --reason TEXT       Why this is approved (recorded)  [required]
  --ttl TEXT          Lifetime, e.g. 30m, 2h (max 24h)  [default: 1h]
  --operation TEXT    Restrict to one exact literal command
  --project-dir TEXT  Repository the approval is bound to
  --help              Show this message and exit.
```

## agentlint approve list

```text
Usage: agentlint approve list [OPTIONS]

  List active approvals.

Options:
  --json  Emit JSON
  --help  Show this message and exit.
```

## agentlint approve revoke

```text
Usage: agentlint approve revoke [OPTIONS] GRANT_ID

  Revoke an approval before it expires.

Options:
  --help  Show this message and exit.
```

## agentlint check

```text
Usage: agentlint check [OPTIONS]

  Evaluate rules against a tool call from stdin.

Options:
  --event TEXT              Hook event type (e.g. PreToolUse, PostToolUse,
                            UserPromptSubmit)  [required]
  --project-dir TEXT        Project directory
  --adapter TEXT            Agent adapter (claude, codex, cursor, gemini, continue,
                            kimi, grok, generic, ...). Auto-detected if not set.
  --format TEXT             Output format override (claude_hooks, cursor_hooks)
  --diagnostic-bundle PATH  Write a sanitized hook diagnostic JSON file
  --help                    Show this message and exit.
```

## agentlint check-patch

```text
Usage: agentlint check-patch [OPTIONS] [PATCH_FILE]

  Preview an apply_patch payload against the same validator and rules as the hook.

  Read-only: no files are written and no session, recording, heartbeat or AgentChute
  queue state is touched. Exits 1 when the patch would be denied.

Options:
  --project-dir TEXT  Project directory (patch paths must stay inside)
  --cwd TEXT          Working directory patch paths are relative to
  --json              Emit machine-readable JSON
  --help              Show this message and exit.
```

## agentlint ci

```text
Usage: agentlint ci [OPTIONS]

  Scan changed files and report violations for CI pipelines.

Options:
  --diff TEXT           Git diff range (e.g., origin/main...HEAD)
  --project-dir TEXT    Project directory
  --format [text|json]
  --help                Show this message and exit.
```

## agentlint ci-setup

```text
Usage: agentlint ci-setup [OPTIONS] [PROVIDER]

  Generate CI configuration for AgentLint.

Options:
  --project-dir TEXT  Project directory
  --dry-run           Print workflow instead of writing it
  --help              Show this message and exit.
```

## agentlint doctor

```text
Usage: agentlint doctor [OPTIONS]

  Diagnose common AgentLint misconfigurations.

  Read-only unless --fix (repairs) or --online (policy refresh) is given.

Options:
  --project-dir TEXT  Project directory
  --fix               Repair common issues automatically
  --online            Also refresh the cloud policy (network call, writes cache)
  --help              Show this message and exit.
```

## agentlint env

```text
Usage: agentlint env [OPTIONS] COMMAND [ARGS]...

  Manage AgentChute shell environment.

Options:
  --help  Show this message and exit.

Commands:
  doctor   Check whether AgentChute env vars are available in this shell/profile.
  install  Persist AgentChute env vars into the shell profile.
  remove   Remove the managed AgentChute env block from the shell profile.
  show     Show AgentChute env status without revealing secrets.
```

## agentlint env doctor

```text
Usage: agentlint env doctor [OPTIONS]

  Check whether AgentChute env vars are available in this shell/profile.

Options:
  --help  Show this message and exit.
```

## agentlint env install

```text
Usage: agentlint env install [OPTIONS]

  Persist AgentChute env vars into the shell profile.

Options:
  --team-key TEXT  AgentChute license key
  --api-url TEXT   AgentChute API URL
  --profile TEXT   Shell profile to update
  --help           Show this message and exit.
```

## agentlint env remove

```text
Usage: agentlint env remove [OPTIONS]

  Remove the managed AgentChute env block from the shell profile.

Options:
  --profile TEXT  Shell profile to update
  --help          Show this message and exit.
```

## agentlint env show

```text
Usage: agentlint env show [OPTIONS]

  Show AgentChute env status without revealing secrets.

Options:
  --help  Show this message and exit.
```

## agentlint evidence

```text
Usage: agentlint evidence [OPTIONS]

  Show verification evidence (test runs, reviews, verified deploys) for this repo.

Options:
  --project-dir TEXT  Repository to show evidence for
  --json              Emit JSON
  --help              Show this message and exit.
```

## agentlint import-agents-md

```text
Usage: agentlint import-agents-md [OPTIONS]

  Import conventions from AGENTS.md into AgentLint config.

Options:
  --project-dir TEXT  Project directory
  --dry-run           Preview config without writing
  --merge             Merge with existing agentlint.yml
  --help              Show this message and exit.
```

## agentlint init

```text
Usage: agentlint init [OPTIONS]

  Initialize AgentLint config in the project.

Options:
  --project-dir TEXT  Project directory
  --team-key TEXT     AgentChute team key. Enables AgentChute in config and prints the
                      env vars to add to your shell or AI tool settings; the secret is
                      not written to disk.
  --help              Show this message and exit.
```

## agentlint list-rules

```text
Usage: agentlint list-rules [OPTIONS]

  List all available rules.

Options:
  --pack TEXT         Filter rules by pack name
  --project-dir TEXT  Project directory
  --help              Show this message and exit.
```

## agentlint login

```text
Usage: agentlint login [OPTIONS]

  Pair this machine with AgentChute through the dashboard.

Options:
  --dashboard-url TEXT  AgentChute dashboard URL
  --api-url TEXT        AgentChute API URL
  --project-dir TEXT    Project directory
  --manual              Paste a license key instead of using dashboard pairing
  --help                Show this message and exit.
```

## agentlint onboard

```text
Usage: agentlint onboard [OPTIONS]

  Guided setup: update, configure AgentChute, install hooks, and smoke test.

Options:
  --project-dir TEXT  Project directory
  --platform TEXT     Coding agent to configure. Repeat or use comma list. Use auto/all.
  --team-key TEXT     AgentChute license key
  --api-url TEXT      AgentChute API URL
  --no-update         Skip AgentLint self-update
  --yes               Accept defaults without prompts
  --open-dashboard    Open the AgentChute dashboard when finished
  --dry-run           Show actions without writing files
  --help              Show this message and exit.
```

## agentlint policy

```text
Usage: agentlint policy [OPTIONS] COMMAND [ARGS]...

  Inspect and refresh cached AgentChute workspace policy.

Options:
  --help  Show this message and exit.

Commands:
  explain  Explain effective cached policy behavior.
  refresh  Refresh cached AgentChute workspace policy.
  status   Show local policy cache status.
```

## agentlint policy explain

```text
Usage: agentlint policy explain [OPTIONS]

  Explain effective cached policy behavior.

Options:
  --format [text|json]
  --help                Show this message and exit.
```

## agentlint policy refresh

```text
Usage: agentlint policy refresh [OPTIONS]

  Refresh cached AgentChute workspace policy.

Options:
  --help  Show this message and exit.
```

## agentlint policy status

```text
Usage: agentlint policy status [OPTIONS]

  Show local policy cache status.

Options:
  --online  Test AgentChute connectivity (no cache changes)
  --help    Show this message and exit.
```

## agentlint queue

```text
Usage: agentlint queue [OPTIONS] COMMAND [ARGS]...

  Inspect and flush the local AgentChute queue.

Options:
  --help  Show this message and exit.

Commands:
  discard-pending  Mark pending AgentChute events delivered without uploading them.
  flush            Flush queued AgentChute events now.
  inspect          Show privacy-safe queued event summaries.
  status           Show local AgentChute queue status.
```

## agentlint queue discard-pending

```text
Usage: agentlint queue discard-pending [OPTIONS]

  Mark pending AgentChute events delivered without uploading them.

Options:
  --yes   Skip confirmation
  --help  Show this message and exit.
```

## agentlint queue flush

```text
Usage: agentlint queue flush [OPTIONS]

  Flush queued AgentChute events now.

Options:
  --max-events INTEGER  Maximum events to flush
  --batch-size INTEGER  Maximum events per API batch
  --time-budget FLOAT   Maximum seconds to spend flushing
  --help                Show this message and exit.
```

## agentlint queue inspect

```text
Usage: agentlint queue inspect [OPTIONS]

  Show privacy-safe queued event summaries.

Options:
  --last INTEGER  Show the last N queued events
  --help          Show this message and exit.
```

## agentlint queue status

```text
Usage: agentlint queue status [OPTIONS]

  Show local AgentChute queue status.

Options:
  --help  Show this message and exit.
```

## agentlint recordings

```text
Usage: agentlint recordings [OPTIONS] COMMAND [ARGS]...

  Manage session recordings.

Options:
  --help  Show this message and exit.

Commands:
  clear  Delete recording files.
  list   Show all recordings (session key, date, event count).
  show   Print formatted timeline for a session.
  stats  Aggregate insights: top tools, top rules fired, patterns.
```

## agentlint recordings clear

```text
Usage: agentlint recordings clear [OPTIONS]

  Delete recording files.

Options:
  --older-than INTEGER  Only delete recordings older than N days
  --yes                 Confirm the action without prompting.
  --help                Show this message and exit.
```

## agentlint recordings list

```text
Usage: agentlint recordings list [OPTIONS]

  Show all recordings (session key, date, event count).

Options:
  --help  Show this message and exit.
```

## agentlint recordings show

```text
Usage: agentlint recordings show [OPTIONS] KEY

  Print formatted timeline for a session.

Options:
  --violations-only  Only show events with violations
  --help             Show this message and exit.
```

## agentlint recordings stats

```text
Usage: agentlint recordings stats [OPTIONS]

  Aggregate insights: top tools, top rules fired, patterns.

Options:
  --last INTEGER  Only include last N sessions
  --help          Show this message and exit.
```

## agentlint report

```text
Usage: agentlint report [OPTIONS]

  Generate session summary report (for Stop event).

Options:
  --project-dir TEXT    Project directory
  --summary             Show cumulative session summary dashboard
  --format [text|json]  Output format (only applies with --summary)
  --adapter TEXT        Agent adapter (claude, codex, cursor, gemini, continue, kimi,
                        grok, generic, ...). Auto-detected if not set.
  --help                Show this message and exit.
```

## agentlint setup

```text
Usage: agentlint setup [OPTIONS] [PLATFORM]

  Install AgentLint hooks into agent settings.

Options:
  --global            Install to user settings
  --project           Install to project settings (default)
  --project-dir TEXT  Project directory
  --dry-run           Show what would be written without modifying files
  --help              Show this message and exit.
```

## agentlint setup-agent

```text
Usage: agentlint setup-agent [OPTIONS]

  Detect and add AgentLint hooks for coding agents.

Options:
  --project-dir TEXT  Project directory
  --platform TEXT     Agent to add. Defaults to detected agents.
  --all               Install hooks for all supported coding agents
  --yes               Install without confirmation
  --help              Show this message and exit.
```

## agentlint status

```text
Usage: agentlint status [OPTIONS]

  Show AgentLint coverage, effective policy and cloud health. Read-only.

Options:
  --project-dir TEXT  Project directory
  --json              Emit machine-readable JSON
  --help              Show this message and exit.
```

## agentlint suppress

```text
Usage: agentlint suppress [OPTIONS] [RULE_ID]

  Suppress a warning rule for the rest of the session.

Options:
  --list         Show suppressed rules
  --clear        Clear all suppressions
  --remove TEXT  Remove a single suppression
  --help         Show this message and exit.
```

## agentlint sync

```text
Usage: agentlint sync [OPTIONS]

  Sync queued AgentChute events now.

Options:
  --background          Bounded background flush mode
  --max-events INTEGER  Maximum queued events to send
  --batch-size INTEGER  Maximum events per API batch
  --time-budget FLOAT   Maximum seconds to spend flushing
  --dry-run             Count events without POSTing
  --help                Show this message and exit.
```

## agentlint test

```text
Usage: agentlint test [OPTIONS]

  Run a safe local and AgentChute end-to-end smoke test.

Options:
  --project-dir TEXT  Project directory
  --flush             Flush the AgentChute queue after enqueueing the test event
  --help              Show this message and exit.
```

## agentlint test-policy

```text
Usage: agentlint test-policy [OPTIONS] TEMPLATE

  Safely simulate a named org-policy template without running a risky command.

Options:
  --project-dir TEXT  Project directory
  --flush             Flush the AgentChute queue after enqueueing the test event
  --no-refresh        Use the cached policy without refreshing from AgentChute
  --help              Show this message and exit.
```

## agentlint uninstall

```text
Usage: agentlint uninstall [OPTIONS] [PLATFORM]

  Remove AgentLint hooks from agent settings.

Options:
  --global            Remove from user settings
  --project           Remove from project settings (default)
  --project-dir TEXT  Project directory
  --help              Show this message and exit.
```

## agentlint update

```text
Usage: agentlint update [OPTIONS]

  Update AgentLint using the detected installer.

Options:
  --dry-run  Print the detected update command without running it
  --help     Show this message and exit.
```
