# AgentLint Roadmap

> **Current state:** v1.0.0 — 64 rules across 8 packs, 1412 tests, 96% coverage.

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

### 1. File-Scope Governance (P1, Size: M)

Security rule that restricts which files an agent can read/write based on glob patterns:
```yaml
rules:
  file-scope:
    allow: ["src/**", "tests/**", "docs/**"]
    deny: ["*.env", "credentials/**", ".github/workflows/**"]
```

PreToolUse rule on Write/Edit/Read. Deny takes precedence over allow. Path normalization resolves symlinks and `../` traversal.

Deferred from v0.4.0 — security-critical, needed for regulated environments (Dar3 fintech).

---

### ~~2. Linter Wrapping~~ → Subsumed by CLI Integration (v1.0.0) ✅

### ~~3. Dependency Vulnerability Scanning~~ → Subsumed by CLI Integration (v1.0.0) ✅

---

### 2. MCP Server for AgentLint (P2, Size: L)

Expose agentlint as an MCP server so Claude can query rules and violations programmatically.

**Resources:**
- `agentlint://rules` — list all rules with metadata
- `agentlint://rules/{rule-id}` — rule detail with examples
- `agentlint://session/violations` — current session violations
- `agentlint://session/state` — session state (edited files, drift count)
- `agentlint://config` — current effective configuration

**Tools:**
- `agentlint.check_content` — check arbitrary content against rules without going through hooks
- `agentlint.toggle_rule` — enable/disable a rule for the current session
- `agentlint.explain_violation` — get detailed explanation + remediation for a violation

The killer feature is `check_content` — lets agents pre-validate code before writing it, avoiding the block-then-retry loop.

---

### ~~3. Dead Code Detection~~ → Subsumed by CLI Integration (v1.0.0) ✅

Configure `ruff check --select F841,F811 {file.path}` or `eslint --rule 'no-unused-vars: error' {file.path}` via CLI integration.

---

### 4. Multi-Project / Monorepo Support (P3, Size: M)

Support monorepos where different subdirectories have different stacks:
```yaml
# agentlint.yml
projects:
  frontend/:
    packs: [universal, frontend, react]
  backend/:
    packs: [universal, python]
  infra/:
    packs: [universal, security]
```

The engine already supports per-directory resolution via `project_dir`. Main work is config parsing + `doctor` validation of project boundaries.

---

### Deferred

**Plugin Settings UI** (P3, Size: M) — Enable severity/pack toggles without editing YAML directly. Requires Claude Code plugin settings API support (not yet available — track upstream).

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
