# Changelog

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
