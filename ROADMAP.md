# AgentLint Roadmap

## v0.4.0 — "The Platform Release" (COMPLETED)

### All 17 Hook Events ✅

- Full `HookEvent` enum: PreToolUse, PostToolUse, Stop, plus 14 passthrough events (SessionStart, SubagentStop, UserPromptSubmit, Notification, etc.)
- CLI routing and plugin hooks.json for all events

### File Content Caching ✅

- PreToolUse caches pre-edit file content → PostToolUse provides `file_content_before` for diff-based rules
- Enables error handling removal detection, test weakening v2, assertion change detection

### Quality Pack (4 rules, always-active) ✅

- `no-error-handling-removal` — detects removal of try/except, null checks, `.catch()`
- `no-dead-imports` — detects unused imports after Write/Edit
- `no-unnecessary-async` — flags unnecessary async/await patterns
- `drift-detector` — tracks edit drift from test runs

### Token Budget Monitoring ✅

- Proxy metrics: tool invocations, content bytes, Bash command lengths
- Configurable thresholds with `warn_at_percent`
- Session activity summary at Stop

---

## v0.5.0 — "The Standards Release" (COMPLETED)

### AGENTS.md Compatibility ✅

- `agentlint import-agents-md` CLI command with `--dry-run` and `--merge` flags
- AGENTS.md parser and heuristic keyword-to-config mapping
- Integrated into stack auto-detection (additive pack discovery)

### Git Auto-Checkpoint ✅

- `git-checkpoint` rule (INFO, disabled by default, opt-in via config)
- Creates `git stash` before destructive operations (`rm -rf`, `git reset --hard`, etc.)
- Automatic cleanup of old checkpoints on session Stop
- Configurable triggers and cleanup schedule

### Plugin Agent Definitions ✅

- `/agentlint:security-audit` — comprehensive codebase security scan
- `/agentlint:doctor` — configuration and hook diagnostics
- `/agentlint:fix` — auto-fix common violations

---

## v0.6.0 — "Progressive Trust" (COMPLETED)

### Circuit Breaker ✅

- Automatic degradation: ERROR → WARNING → INFO → suppressed based on fire count thresholds
- Security-critical rules (`no-secrets`, `no-env-commit`) exempt — always block
- Time-based and clean-evaluation auto-reset
- Session report includes circuit breaker status section
- Fully configurable globally and per-rule
- Hardened: defensive coding for corrupted session state, logging for transitions

### Tests ✅

- 812 tests, 96% coverage

---

## v0.7.0+ Backlog

### Governance / File-Scope Enforcement (Priority: P1, Size: L)

Security rule that restricts which files an agent can read/write based on glob patterns:
```yaml
governance:
  file_scope:
    allow: ["src/**", "tests/**", "docs/**"]
    deny: ["*.env", "credentials/**", ".github/workflows/**"]
```

Deferred from v0.4.0 — security-critical, needs careful path normalization design.

---

### Linter Wrapping (Priority: P2, Size: L)

PostToolUse rule that runs the project's configured linter on changed files after Write/Edit:
```yaml
run-linter:
  commands:
    python: "ruff check {file}"
    typescript: "npx eslint {file}"
  timeout: 10
```

Needs shared subprocess architecture (same infra as dependency scanning). Most complex feature in the roadmap.

---

### Dependency Vulnerability Scanning (Priority: P2, Size: L)

PostToolUse rule that fires when `package.json`, `pyproject.toml`, `requirements.txt`, or `Cargo.toml` is modified.

**Approach:** Wrap existing tools:
- Python: `pip-audit` or `safety check`
- JavaScript: `npm audit` or `yarn audit`
- Go: `govulncheck`
- Rust: `cargo audit`

**Config:**
```yaml
rules:
  dependency-audit:
    tools:
      python: "pip-audit"
      javascript: "npm audit --json"
    severity_threshold: "high"  # only report high/critical CVEs
```

---

### MCP Server for AgentLint (Priority: P2, Size: L)

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

---

### Plugin Settings UI (Priority: P3, Size: M)

Enable severity/pack toggles without editing YAML directly. Plugin-level settings schema:
```json
{
  "settings": {
    "severity": { "type": "enum", "values": ["strict", "standard", "relaxed"], "default": "standard" },
    "packs": { "type": "multiselect", "values": ["universal", "python", "frontend", "react", "seo", "security"] }
  }
}
```

Requires Claude Code plugin settings API support (not yet available — track upstream).

---

### Dead Code Detection (Priority: P3, Size: L)

PostToolUse rule that detects unreachable or unused code after Write/Edit:
- Unreachable code after `return`, `raise`, `break`
- Unused variables in the written/edited function
- Functions defined but never called within the file

**Limitation:** Requires AST parsing (not just regex). Would need `ast` module for Python, TypeScript compiler API for TS. Significantly more complex than regex-based rules.

---

### Multi-Project / Monorepo Support (Priority: P3, Size: M)

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
