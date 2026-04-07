# AgentLint Roadmap

> **Current state:** v1.1.0 — 65 rules across 8 packs, 1432 tests, 96% coverage.

---

## Completed Releases

### v0.4.0 — "The Platform Release" ✅

- **All 17 Hook Events** — Full `HookEvent` enum: PreToolUse, PostToolUse, Stop, plus 14 passthrough events (SessionStart, SubagentStop, UserPromptSubmit, Notification, etc.)
- **File Content Caching** — PreToolUse caches pre-edit content → PostToolUse provides `file_content_before` for diff-based rules
- **Quality Pack (4 rules, always-active)** — `no-error-handling-removal`, `no-dead-imports`, `commit-message-format`, `self-review-prompt`
- **Token Budget Monitoring** — proxy metrics, configurable thresholds, session activity summary

### v0.5.0 — "The Standards Release" ✅

- **AGENTS.md Compatibility** — `agentlint import-agents-md` with `--dry-run` and `--merge` flags
- **Git Auto-Checkpoint** — `git-checkpoint` rule (INFO, disabled by default, opt-in)
- **Plugin Agent Definitions** — `/agentlint:security-audit`, `/agentlint:doctor`, `/agentlint:fix`

### v0.6.0 — "Progressive Trust" ✅

- **Circuit Breaker** — automatic degradation (ERROR → WARNING → INFO → suppressed) based on fire count. Security-critical rules exempt. Time-based and clean-evaluation auto-reset.

### v0.7.0 — "Autopilot Pack" ✅

14 production-grade guardrails for unattended/autonomous sessions:

- **Infrastructure:** `production-guard`, `cloud-resource-deletion`, `cloud-infra-mutation`, `cloud-paid-resource-creation`, `network-firewall-guard`, `docker-volume-guard`, `system-scheduler-guard`
- **Session safety:** `destructive-confirmation-gate`, `dry-run-required`, `bash-rate-limiter`, `cross-account-guard`, `operation-journal`
- **Universal additions:** `cicd-pipeline-guard`, `package-publish-guard`
- **Security addition:** `env-credential-reference`

### v0.8.0 — "Subagent Safety" ✅

- **Subagent Lifecycle Hooks** — `subagent-safety-briefing` (SubagentStart), `subagent-transcript-audit` (SubagentStop)
- **Session Report** — subagent activity section with spawn counts, audit results, agent_id disambiguation

### v0.9.0 — "Remote Server Safety" ✅

4 new autopilot rules for SSH/chroot operations:

- `ssh-destructive-command-guard` — detects destructive commands via SSH (WARNING/ERROR)
- `remote-boot-partition-guard` — blocks rm/dd targeting `/boot` kernel files
- `remote-chroot-guard` — detects bootloader removal and risky repair inside chroot
- `package-manager-in-chroot` — warns on apt/yum/dnf/pacman inside chroot

Also: per-pattern severity (individual violations can override rule severity).

### v0.9.8 — "Agent-Visible Advisory Output" ✅

PostToolUse and PreToolUse advisory violations (WARNING/INFO) now use `additionalContext` (agent-visible) instead of `systemMessage` (user-only). PostToolUse WARNING uses `decision: "block"` as strong advisory signal.

### v0.9.9 — "First-Class Custom Packs" ✅

Custom packs are first-class citizens:

- `packs:` list controls activation for both built-in and custom packs
- `list-rules --pack fintech` shows custom rules
- `doctor` validates `custom_rules_dir` and detects orphaned packs
- Config no longer warns about "unknown pack" when `custom_rules_dir` is set

### v0.9.10 — "Status Count Fix" ✅

- `status` active rule count now excludes orphaned custom rules

### v1.0.0 — "CLI Integration" ✅

Generic subprocess execution rule that subsumes linter wrapping, dependency scanning, and dead code detection. Configure any CLI tool as a PostToolUse check with template placeholders, glob filters, timeouts, and severity levels. All placeholder values shell-escaped via `shlex.quote()` for injection prevention.

### Unplanned Features Shipped (not in original roadmap)

- **Session Recordings** (v0.9.x) — `recordings {list,show,stats,clear}` for session replay and product insights
- **Python Pack** (6 rules) — `no-bare-except`, `no-dangerous-migration`, `no-sql-injection`, `no-unnecessary-async`, `no-unsafe-shell`, `no-wildcard-import`
- **Frontend Pack** (8 rules) — accessibility, responsive patterns, touch targets, style rules
- **React Pack** (3 rules) — empty states, lazy loading, query loading state
- **SEO Pack** (4 rules) — Open Graph, metadata, semantic HTML, structured data

---

## Backlog — Prioritized

### 1. File-Scope Governance (P1, Size: M) — PR #24

Security rule that restricts which files an agent can read/write based on allow/deny glob patterns. Deny takes precedence. Blocks Write, Edit, Read, and Bash file operations. Path traversal blocked via `os.path.realpath()`.

---

### 2. Quality Rules from Reddit Research (P1, Size: M)

Three new rules addressing top community pain points:

- **`no-large-diff`** (quality, PostToolUse, WARNING) — Warns when a single Write/Edit produces a diff larger than a threshold. Forces smaller, reviewable chunks. Uses `file_content_before` diff. Config: `max_lines_added: 200`, `max_lines_removed: 100`.

- **`no-file-creation-sprawl`** (quality, PostToolUse, WARNING) — Tracks files created during the session. Warns after N new files. Encourages extending existing files. Config: `max_new_files: 10`.

- **`naming-conventions`** (quality, PreToolUse, INFO) — Checks file names against configurable patterns (snake_case for Python, camelCase/PascalCase for JS/TS, test_ prefix).

---

### 3. CI Mode (P2, Size: M)

`agentlint ci` command that scans a git diff and exits non-zero on violations. Runs the same rules and config as hooks, but triggered in CI pipelines instead of Claude Code.

```yaml
# .github/workflows/agentlint.yml
name: AgentLint
on: [pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: pip install agentlint
      - run: agentlint ci --diff origin/main...HEAD
```

**Design:**
- `git diff --name-only` to get changed files
- For each file: read content, build RuleContext with event=PostToolUse, evaluate
- Report violations in human-readable format (not JSON hook protocol)
- Exit 0 = clean, exit 1 = violations found
- Respects `agentlint.yml` config (packs, severity, rule overrides)
- `--format json` option for CI integrations that parse output

**Why:** Agentlint becomes a second line of defense — catches violations even when developers don't use Claude Code. Makes agentlint a "code quality platform" not just a "Claude Code plugin."

---

### 4. Doctor CLI Integration Recipes (P2, Size: S)

When `doctor` detects project tools in PATH (ruff, eslint, mypy, pytest), suggest CLI integration config snippets. Low effort, high discoverability.

---

### 5. MCP Server (P2, Size: L)

Expose agentlint as an MCP server. Resources: rules, config, session state. Tools: `check_content` (pre-validate code), `toggle_rule`, `list_rules`. The killer feature is `check_content` — agents pre-validate before writing, avoiding the block-then-retry loop.

---

### 6. Multi-Project / Monorepo Support (P3, Size: M)

Per-subdirectory pack configuration via `projects:` config key. The engine already supports per-directory resolution. Main work is config parsing + `doctor` validation.

---

### Completed (originally in backlog)

- ~~Linter Wrapping~~ → Subsumed by CLI Integration (v1.0.0)
- ~~Dependency Vulnerability Scanning~~ → Subsumed by CLI Integration (v1.0.0)
- ~~Dead Code Detection~~ → Subsumed by CLI Integration (v1.0.0). Configure `ruff --select F841` or `eslint no-unused-vars` via CLI integration.

### Deferred

**Plugin Settings UI** (P3, Size: M) — Requires Claude Code plugin settings API support (not yet available — track upstream).

---

## After the Backlog — What's Next

### GitHub Actions Marketplace Action (P1 post-backlog)

`mauhpr/agentlint-action` — one-line reusable action for any repo:

```yaml
- uses: mauhpr/agentlint-action@v1
```

Posts violations as inline PR review comments. Requires CI mode (backlog #3) to ship first. ~30 lines of action config wrapping `agentlint ci`. This is the single highest-leverage growth move — makes agentlint visible on every PR.

### Community Growth

- Example configs for popular stacks (Rails, Django, Next.js, Rust, Go)
- Blog posts: "How to prevent your AI agent from deleting production" (Reddit signal: 2800+ upvotes)
- `agentlint init` generates better defaults per detected stack

### Other Agent Tools

- **Cursor** — AfterFileEdit / BeforeShellExecution hooks (similar to Claude Code)
- **Aider** — post-edit hook integration
- **Codex / OpenAI Agents** — if they adopt a hook protocol

CI mode covers all of these indirectly — if agentlint runs in the pipeline, the coding tool doesn't matter.

### Enterprise (on demand)

- Team-level config inheritance (org → repo → project)
- Centralized rule management
- Reporting dashboard (session recordings infra already exists)

Build when someone asks and is willing to pay. Not before.

---

## Competitor Landscape

| Tool | Approach | Differentiator vs AgentLint |
|------|----------|---------------------------|
| [disler/claude-code-hooks-mastery](https://github.com/disler/claude-code-hooks-mastery) | Example hooks (3,000+ stars) | Not a framework — agentlint is packaged + auto-detecting |
| [rulebricks/claude-code-guardrails](https://github.com/rulebricks/claude-code-guardrails) | Cloud-based rule engine | Agentlint is local-first, no cloud dependency |
| [Codacy Guardrails](https://www.codacy.com/guardrails) | MCP-based, enterprise | Agentlint is open-source, hook-based (lighter) |
| [wangbooth/Claude-Code-Guardrails](https://github.com/wangbooth/Claude-Code-Guardrails) | Git-focused guardrails | Narrower scope — agentlint covers more categories |
| [Aider](https://aider.chat/) | Lint/test integration | Aider wraps linters; agentlint defines rules + wraps linters |
| [Kiro.dev](https://kiro.dev/) | Spec-driven IDE | Different category (IDE vs. plugin) |
| Cursor Rules / .cursorrules | IDE-specific conventions | Not enforceable — suggestions, not requirements |

**AgentLint's positioning:** "If it's a suggestion, use CLAUDE.md. If it's a requirement, use AgentLint."
