# Changelog

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
