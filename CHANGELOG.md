# Changelog

## v0.9.9 (2026-04-02) — First-Class Custom Packs

### The change

Custom packs are now first-class citizens. Add your custom pack name to `packs:` and it works everywhere:

- `list-rules --pack fintech` shows your custom rules
- `doctor` warns when custom rules have orphaned packs (pack not in `packs:`)
- `init` template hints at custom pack usage
- Config no longer warns about "unknown pack" when `custom_rules_dir` is set

### Fixes

- **`list-rules` now shows custom rules** — previously only showed built-in packs
- **`list-rules --pack <name>` works for custom packs** — `--pack fintech` filters to fintech rules only
- **`list-rules --pack universal` includes custom rules with `pack = "universal"`** — was silently hiding them
- **`doctor` validates `custom_rules_dir`** — warns if directory missing, empty, or packs orphaned
- **reporter.py docstring updated** — accurately reflects additionalContext usage

### Tests

1356 tests, 96% coverage.

## v0.9.8 (2026-03-31) — Advisory Output Now Influences Agent Behavior

### The problem

PostToolUse and PreToolUse advisory violations (WARNING/INFO) were delivered via `systemMessage`, which is a user-facing notification only. The agent saw the text but had no protocol-level reason to act on it — explaining why rules like `no-unnecessary-async` were routinely ignored.

### Fix

Advisory output now uses the correct Claude Code hook protocol channels:

- **PreToolUse advisory** (WARNING/INFO, no errors): `hookSpecificOutput.additionalContext` — injected into agent context before tool runs
- **PostToolUse WARNING**: `decision: "block"` + `reason` + `additionalContext` — strongest advisory signal
- **PostToolUse INFO**: `hookSpecificOutput.additionalContext` — agent sees it in reasoning context
- **Other events** (Stop, Notification): `systemMessage` unchanged

### Tests

1345 tests, 96% coverage.

## v0.9.7 (2026-03-30) — Git mv/cp False Positive Fix

### Fixes

- **`no-bash-file-write` false positive on `git mv`** — The `mv` and `cp` regex patterns matched `git mv` and `git cp`, flagging VCS renames as file writes. Fix: negative lookbehind excludes `git ` prefix from both write patterns and target path extractors.

### Tests

1340 tests, 96% coverage.

## v0.9.6 (2026-03-30) — Cross-Account Guard Fix

### Fixes

- **`cross-account-guard` false positive** — `\S+` regex captured trailing shell metacharacters (`)`, `;`, `|`, `&`) from subshell expressions like `$(gcloud --project=foo)`, causing the same project ID to look like two different projects. Fix: strip trailing shell syntax from extracted project/profile names.

### Tests

1337 tests, 96% coverage.

## v0.9.0 (2026-03-05) — Remote Server Safety

### The problem

SSH and chroot operations on remote servers have extreme blast radius — no physical access for recovery. Existing autopilot rules covered cloud APIs but not raw shell-level server operations.

### New rules (4 autopilot)

- **`ssh-destructive-command-guard`** (WARNING/ERROR) — Detects destructive commands via SSH: `rm -rf`, `mkfs`, `dd`, `reboot`, `iptables flush`, `terraform destroy`. ERROR for catastrophic patterns, WARNING for risky ones.
- **`remote-boot-partition-guard`** (ERROR) — Blocks `rm` or `dd` targeting `/boot` kernel and bootloader files via SSH.
- **`remote-chroot-guard`** (WARNING/ERROR) — Detects bootloader package removal and risky repair commands inside chroot environments. ERROR for bootloader removal, WARNING for risky repair.
- **`package-manager-in-chroot`** (WARNING) — Warns on `apt`/`dpkg`/`yum`/`dnf`/`pacman` usage inside chroot environments.

### Fixes

- **`allowed_ops` consistency** — All autopilot rules now use `allowed_ops` config key consistently.
- **Per-pattern severity** — Individual `Violation` instances can override `Rule.severity` for mixed WARNING/ERROR rules.
- **`rm --recursive` detection** — Long-form `--recursive` flag now detected alongside `-rf`.
- **`apt-get` detection** — Package manager rules now detect `apt-get` in addition to `apt`.

### Rule count

63 rules across 8 packs (was 59/8). 18 autopilot rules (was 14).

### Tests

1229 tests, 96% coverage.

## v0.8.0 (2026-03-02) — Subagent Safety

### The problem

Claude Code's hooks fire on the **parent session only**. When a subagent spawns (via the Agent tool), its Bash/Write/Edit calls do not trigger parent PreToolUse hooks. AgentLint's blocking rules had zero protection for subagent actions.

### New: Subagent safety (2 autopilot rules)

- **`subagent-safety-briefing`** (INFO, SubagentStart) — Injects a safety notice into the subagent's context via `additionalContext`, warning it about the lack of real-time guardrails and advising against destructive infrastructure commands.
- **`subagent-transcript-audit`** (WARNING, SubagentStop) — Reads the subagent's JSONL transcript and scans all Bash commands against dangerous patterns (destructive ops, cloud deletions, firewall mutations, production DB access, git force push). Findings appear in the session Stop report.

### New: Plugin agent frontmatter hooks

- AgentLint's own plugin agents (`doctor`, `fix`, `security-audit`) now include `PreToolUse` frontmatter hooks for **real-time blocking** protection inside the subagent context.

### Fixes

- **SubagentStop field mapping** — Fixed `subagent_output` to read from `last_assistant_message` (correct Claude Code protocol field name). Falls back to `subagent_output` for backward compatibility.
- **RuleContext fields** — Added `agent_transcript_path`, `agent_type`, `agent_id` fields to `RuleContext`. All propagated through CLI context re-creation blocks.

### Infrastructure

- **SubagentStart hook registered** — `agentlint setup` and the plugin now register the SubagentStart hook event (was missing).
- **Reporter** — New `format_subagent_start_output()` method for SubagentStart additionalContext injection. Session report includes "Subagent Activity" section with spawn and audit data.
- **CLI routing** — SubagentStart events routed to the new format method instead of generic `format_hook_output()`.

### Documentation

- New [docs/subagent-safety.md](docs/subagent-safety.md) — explains the limitation, what AgentLint does, how to protect your own subagents, and known limitations.
- README updated with subagent safety note in autopilot pack section.

### Rule count

59 rules across 8 packs (was 57/8). 14 autopilot rules (was 12).

### Tests

1128 tests, 96% coverage.

## v0.7.1 (2026-03-02) — Vision & framing

- README: expanded tagline to "code quality, security, and infrastructure safety"
- README: added Vision section explaining the short-term (code quality) and longer-term (autonomous agent infrastructure safety) goals; honest about what's solved vs. what's still an open problem

## v0.7.0 (2026-03-02) — Autopilot Safety Pack

### New: `autopilot` pack (12 rules, opt-in, ⚠️ alpha)

> **Experimental.** Regex-based heuristics for cloud and infrastructure safety. Expect false positives. A mature framework for autonomous agent guardrails doesn't exist yet — this is an early experiment, not a production-hardened solution. Use at your own risk and report what breaks.

Add to `agentlint.yml` to enable:
```yaml
packs:
  - universal
  - autopilot
```

- **`production-guard`** — Blocks Bash commands targeting production databases (psql/mysql with prod host/db name), gcloud projects, or AWS accounts. Configurable `allowed_projects` and `allowed_hosts` allowlists.
- **`destructive-confirmation-gate`** — Blocks DROP DATABASE, DROP TABLE, terraform destroy, kubectl delete namespace, and gcloud/heroku project deletion unless `session_state['confirmed_destructive_ops']` contains an explicit acknowledgment key.
- **`dry-run-required`** — Requires --dry-run/--check/plan preview before terraform apply, kubectl apply, ansible-playbook, helm upgrade/install, and pulumi up.
- **`bash-rate-limiter`** — Circuit-breaks after N destructive commands within a time window (default: 5 ops / 300s), preventing runaway autonomous loops.
- **`cross-account-guard`** — Warns when the agent switches between gcloud projects or AWS profiles mid-session.
- **`operation-journal`** — Records every Bash and file-write operation to an in-session audit log; emits a summary at Stop.
- **`cloud-resource-deletion`** — Blocks AWS/GCP/Azure resource deletion without session confirmation.
- **`cloud-infra-mutation`** — Blocks NAT, firewall, VPC, IAM, and load balancer mutations across AWS/GCP/Azure.
- **`cloud-paid-resource-creation`** — Warns when creating paid cloud resources (VMs, DBs, static IPs).
- **`system-scheduler-guard`** — Warns on crontab, systemctl enable, launchctl, and scheduler file writes.
- **`network-firewall-guard`** — Blocks iptables flush, ufw disable, firewalld permanent rules, and default route changes.
- **`docker-volume-guard`** — Blocks privileged containers (ERROR); warns on volume deletion and force-remove (WARNING).

### Bug fixes
- `env-credential-reference`: Secret Manager references (`Secret:`, `secretmanager:`) no longer trigger false positive on Pattern 1.
- `env-credential-reference`: Quoted Cloud Run `--set-env-vars` values now correctly matched by Pattern 3.
- `system-scheduler-guard`: `crontab -u myuser` (read-only) no longer triggers a false positive; `-r` (remove) now correctly warns.

### UX improvements
- `docker-volume-guard`: Added `allowed_ops` config bypass.
- `network-firewall-guard`: Added `allowed_ops` config bypass.
- `cloud-infra-mutation`: Renamed `allowed_operations` → `allowed_ops` for consistency.

### Rule count
57 rules across 8 packs (was 42/7).

### Tests
1061 tests, 96% coverage.

## 0.6.0 (2026-02-24) — "Progressive Trust"

Automatic circuit breaker prevents buggy rules from locking agents in a loop.

### New: Circuit Breaker (ON by default)

- **Automatic degradation** — When a blocking rule (ERROR) fires 3+ times in a session, it degrades to WARNING (advisory). Fires 6+ times → INFO. Fires 10+ times → suppressed. Prevents false positive loops from blocking agents.
- **Security-critical rules exempt** — `no-secrets` and `no-env-commit` never degrade by default. All other rules can opt-out via per-rule config.
- **Auto-reset** — 5 consecutive clean evaluations or 30 minutes without fire resets the circuit breaker to ACTIVE.
- **Session report transparency** — Stop report includes "Circuit Breaker" section showing which rules were degraded and their fire counts.
- **Fully configurable** — Global thresholds in `circuit_breaker:` config block. Per-rule overrides via `rules: <rule-id>: circuit_breaker:`.

### Configuration

```yaml
# Global defaults (can be overridden)
circuit_breaker:
  enabled: true          # ON by default
  degraded_after: 3      # ERROR → WARNING
  passive_after: 6       # → INFO
  open_after: 10         # → suppressed
  reset_after_clean: 5   # reset after 5 clean evals
  reset_after_minutes: 30

# Per-rule override
rules:
  no-secrets:
    circuit_breaker: { enabled: false }  # never degrade (default)
```

### Tests

- 812 tests, 96% coverage

## 0.5.3 (2026-02-24) — "Actually Blocks Now"

Critical fix: PreToolUse blocking now actually works. Plus fork bomb false positive fix.

### Fixes

- **PreToolUse blocking protocol** — AgentLint was outputting `{"systemMessage": "BLOCKED: ..."}` with exit code 2, but Claude Code ignores JSON on exit 2. Now uses the correct `hookSpecificOutput` deny protocol: exit 0 + `{"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "..."}}`. **This means blocking rules (no-secrets, no-force-push, no-env-commit, security pack) now actually prevent tool execution.**
- **Fork bomb false positive** — The `no-destructive-commands` regex for fork bombs included `/dev/null\s*\|` which matched any command using `2>/dev/null | pipe` — one of the most common shell idioms. Commands like `printenv | grep 2>/dev/null | head` and `gcloud sql instances list 2>/dev/null | head` were incorrectly flagged. Removed the overly broad pattern.

### Tests

- 759 tests (12 new), 96% coverage

## 0.5.2 (2026-02-24) — "Self-Audit Fix"

Fixes two issues found by auditing AgentLint's own behavior in a real session.

### Fixes

- **`no-bash-file-write` heredoc false positive** — Commands using `$(cat <<'EOF' ...)` for passing multi-line strings (e.g. `git commit -m`, `gh pr create --body`) are no longer flagged as file writes. Real heredoc file writes (`cat << EOF > file.txt`) are still blocked.
- **Session report "Files changed: 0"** — The Stop report now tracks files touched during the session (accumulated from PreToolUse/PostToolUse events) instead of relying solely on `git diff --name-only HEAD`, which returns nothing after a commit.

### Tests

- 747 tests (6 new), 96% coverage

## 0.5.1 (2026-02-22) — "It Just Works"

Fix installation UX so `pip install agentlint` + plugin install works with zero manual PATH hacking.

### Fixes

- **Add `__main__.py`** — `python -m agentlint` now works, fixing the broken fallback in `_resolve_command()`
- **Robust binary resolution** — `_resolve_command()` now probes 5 locations: `shutil.which()`, `~/.local/bin/` (pipx), `~/.local/share/uv/tools/` (uv), `sysconfig.get_path("scripts")` (pip console_scripts), and `sys.executable -m agentlint`. The sysconfig probe is the key fix for macOS Framework Python installs (e.g. `/Library/Frameworks/Python.framework/Versions/3.13/bin/`)
- **Sync plugin directory** — `plugin/hooks/hooks.json` now uses `resolve-and-run.sh` instead of bare `agentlint`, and includes all 6 events (was missing UserPromptSubmit, SubagentStop, Notification)
- **Add `plugin/bin/resolve-and-run.sh`** — binary resolver script with sysconfig probe, matching the agentlint-plugin repo

## 0.5.0 (2026-02-22) — "The Standards Release"

AgentLint aligns with the AGENTS.md industry standard, adds git safety checkpoints, and ships plugin agent definitions.

### New: AGENTS.md Compatibility

- **`agentlint import-agents-md`** — New CLI command that reads AGENTS.md from project root, extracts conventions, and generates/merges agentlint.yml config
- `--dry-run` flag to preview without writing
- `--merge` flag to merge with existing agentlint.yml
- Stack auto-detection now uses AGENTS.md hints to discover additional packs
- Conservative mapping: inferred rules use INFO severity

### New: Git Auto-Checkpoint

- **`git-checkpoint`** (INFO) — Creates a `git stash` safety checkpoint before destructive operations (`rm -rf`, `git reset --hard`, `git checkout .`, `git clean -fd`, `DROP TABLE/DATABASE`)
- **Disabled by default** — opt in with `git-checkpoint: { enabled: true }` in config
- Configurable trigger patterns and cleanup schedule
- Automatic cleanup of old checkpoints (default: 24h) on session Stop
- First guardrail tool to offer automatic pre-destructive recovery points

### New: Plugin Agent Definitions

- **`/agentlint:security-audit`** — Comprehensive security audit agent that scans for secrets, unsafe patterns, and env file issues
- **`/agentlint:doctor`** — Diagnostic agent for configuration and hook installation issues
- **`/agentlint:fix`** — Auto-fix agent for common violations (debug artifacts, accessibility, dead imports)

### Tests

- 729 tests (90 new), 96% coverage

## 0.4.0 (2026-02-22) — "The Platform Release"

### Full lifecycle coverage — 17 hook events

AgentLint now supports all 17 Claude Code hook events (up from 4), making it the first guardrail tool with complete lifecycle coverage:
- **New events**: SessionEnd, UserPromptSubmit, SubagentStart, SubagentStop, Notification, PreCompact, PostToolUseFailure, PermissionRequest, ConfigChange, WorktreeCreate, WorktreeRemove, TeammateIdle, TaskCompleted
- Events without dedicated rules pass through gracefully (exit 0)

### New: Quality pack (always-active)

- **`commit-message-format`** (WARNING) — Validates git commit messages follow conventional commits format. Configurable `max_subject_length` and `format` (conventional/freeform).
- **`no-dead-imports`** (INFO) — Detects unused imports in Python and JS/TS files. Skips `__init__.py`, `index.ts`, and configurable ignore list.
- **`no-error-handling-removal`** (WARNING) — Warns when error handling patterns (try/except, .catch, ErrorBoundary) are completely removed from code. Uses file content caching for diff-based detection.
- **`self-review-prompt`** (INFO) — Injects an adversarial self-review prompt at session end to catch bugs. Customizable via `custom_prompt` config.

### New universal rule

- **`token-budget`** (WARNING/INFO) — Tracks session activity (tool invocations, content bytes, duration). Warns at configurable threshold (default: 80% of 200 calls). Reports session activity summary at Stop.

### New CLI commands

- **`agentlint status`** — Shows version, severity mode, active packs, rule count, and session activity
- **`agentlint doctor`** — Diagnoses common misconfigurations: config file, hooks installation, Python version, session cache

### Engine enhancements

- **File content caching** — PreToolUse for Write/Edit now caches current file content in session state. PostToolUse provides `file_content_before` for diff-based rules.
- **Extended RuleContext** — New fields: `prompt` (UserPromptSubmit), `subagent_output` (SubagentStop), `notification_type` (Notification), `compact_source` (PreCompact), `file_content_before` (diff support).

### Hook registration

- `agentlint setup` now registers hooks for UserPromptSubmit, SubagentStop, and Notification events in addition to PreToolUse, PostToolUse, and Stop.

### Tests

- 639 tests (82 new), 96% coverage

## 0.3.0 (2026-02-22) — "The Security Release"

### New: Security pack (opt-in)

- **`no-bash-file-write`** (ERROR) — Blocks file writes via Bash that bypass Write/Edit guardrails: `cat >`, `tee`, `echo >`, `sed -i`, `printf >`, `cp`, `mv`, `perl -pi -e`, `awk >`, `dd of=`, heredocs, `python -c`. Configurable `allow_patterns` and `allow_paths`.
- **`no-network-exfil`** (ERROR) — Blocks potential data exfiltration via `curl POST`, `curl -d @file`, `nc`, `scp`, `wget --post-file`, `python requests.post()`, `rsync` with sensitive files. Configurable `allowed_hosts`.

### New universal rules

- **`no-push-to-main`** (WARNING) — Warns on direct `git push origin main/master`
- **`no-skip-hooks`** (WARNING) — Warns on `git commit --no-verify` or `--no-gpg-sign`
- **`no-test-weakening`** (WARNING) — Detects patterns that weaken test suites: `@pytest.mark.skip`, `assert True`, commented-out assertions, empty test functions, `@pytest.mark.xfail` without reason

### Enhanced existing rules

- **`no-secrets`** — New patterns: Slack tokens (`xoxb-`, `xoxp-`, `xoxs-`), private keys (`-----BEGIN...PRIVATE KEY-----`), GCP service accounts, database connection strings, JWT tokens, `.npmrc` auth tokens, Terraform state, `curl` with embedded credentials, `github_pat_` prefix. New `extra_prefixes` config option.
- **`no-destructive-commands`** — New patterns: `chmod 777`, `mkfs`, `dd if=/dev/zero`, fork bombs, `docker system prune -a --volumes`, `kubectl delete namespace`, `git branch -D` on protected branches. Per-pattern severity: catastrophic patterns (`rm -rf /`, `mkfs`, fork bombs) now return ERROR instead of WARNING.
- **`no-env-commit`** — Now detects `.env` writes via Bash (`echo > .env`, `cat > .env`, `tee .env`, `cp`, `sed -i`, heredocs)

### New CLI command

- **`agentlint list-rules`** — Lists all available rules with pack, event, severity, and description. Supports `--pack` filter.

### Tests

- 547 tests (118 new), 95% coverage

## 0.2.1 (2026-02-20)

### Fixes

- `agentlint setup` now resolves the absolute path to the `agentlint` binary at install time, fixing `command not found` errors when Claude Code runs hooks via `/bin/sh` with a minimal PATH
- Fallback chain: `shutil.which("agentlint")` → `sys.executable -m agentlint` → bare `agentlint`
- Works with all installation methods: pip, pipx, uv tool, uv pip (venv), poetry, system Python

### Tests

- 429 tests (19 new), 95% coverage

## 0.2.0 (2026-02-20)

### New packs — 21 new rules

- **Python** (6 rules): `no-bare-except`, `no-unsafe-shell`, `no-dangerous-migration`, `no-wildcard-import`, `no-unnecessary-async`, `no-sql-injection`
- **Frontend** (8 rules): `a11y-image-alt`, `a11y-form-labels`, `a11y-interactive-elements`, `a11y-heading-hierarchy`, `mobile-touch-targets`, `mobile-responsive-patterns`, `style-no-arbitrary-values`, `style-focus-visible`
- **React** (3 rules): `react-query-loading-state`, `react-empty-state`, `react-lazy-loading`
- **SEO** (4 rules): `seo-page-metadata`, `seo-open-graph`, `seo-semantic-html`, `seo-structured-data`

### Infrastructure

- Stack auto-detection: packs activate based on project files (`pyproject.toml`, `package.json`, SSR/SSG framework dependencies)
- Shared `_helpers.py` modules for frontend and SEO file type detection
- All packs registered in `PACK_MODULES` with lazy detection functions

### Tests

- 410 tests (172 new), 95% coverage

## 0.1.1 (2026-02-19)

### Fixes

- Handle `EOFError` on empty stdin in `check` and `report` commands
- Catch YAML parse errors in config loading — invalid YAML now logs a warning and uses defaults
- Move inline `import os` to module level in `no_secrets` rule
- Detect `pip3 install` in addition to `pip install` in `dependency-hygiene` rule

### Tests

- Add 9 new tests (238 total, 96% coverage): empty stdin, YAML errors, env var fallback, path traversal, custom thresholds, nested `.env` paths, case-insensitive branch names, `pip3`

### Documentation

- Add FAQ section to README
- Add example output to Quick Start showing what blocking looks like
- Add YAML cheat sheet to configuration reference
- Add rule discovery and debugging tips to custom rules guide
- Add "First timer? Start here" section to CONTRIBUTING.md
- Add PyPI classifiers and keywords to pyproject.toml

## 0.1.0 (2026-02-17)

Initial release.

### Features

- Core engine with rule evaluation, severity overrides, and session state
- 10 universal rules: no-secrets, no-env-commit, no-force-push, no-destructive-commands, dependency-hygiene, max-file-size, drift-detector, no-debug-artifacts, test-with-changes, no-todo-left
- CLI commands: `agentlint check`, `agentlint init`, `agentlint report`, `agentlint setup`, `agentlint uninstall`
- `agentlint setup` — one-command hook installation into Claude Code settings
- `agentlint uninstall` — clean removal of AgentLint hooks from Claude Code settings
- YAML configuration with auto-detection fallback
- Claude Code plugin with PreToolUse, PostToolUse, and Stop hooks
- Claude Code marketplace support — install via `/plugin marketplace add mauhpr/agentlint`
- Custom rules directory support
- Session state persistence across hook invocations
- Three severity modes: strict, standard, relaxed
