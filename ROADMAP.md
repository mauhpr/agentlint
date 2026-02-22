# AgentLint Roadmap

## v0.4.0 — "The Platform Release"

Engine grows up: new hook events, governance config, linter wrapping, quality pack.

### New Hook Events (Size: L)

Claude Code v2.1.0 added events that agentlint doesn't support yet. Adding them unlocks new rule categories.

**Engine changes:**
- Add to `HookEvent` enum: `SessionStart` (exists but unused), `SessionEnd`, `SubagentStop`, `UserPromptSubmit`, `PreCompact`
- Add CLI routing for each new event
- Update `setup.py` `build_hooks()` to register new events
- Update plugin `hooks/hooks.json` with new entries

**New rules enabled by new events:**
- `SessionStart` — Initialize session config, log session start, enforce governance policies
- `SessionEnd` — Final cleanup, comprehensive session report (richer than current Stop)
- `UserPromptSubmit` — Pre-process user prompts, enforce governance policies
- `SubagentStop` — Validate subagent outputs before they propagate
- `PreCompact` — Inject "remember agentlint rules" message before context compression

**Compatibility:** Needs version detection — older Claude Code won't fire new events.

---

### Governance / Policy Configuration (Size: L)

GitHub issue [#26714](https://github.com/anthropics/claude-code/issues/26714) formally requests `.claude/governance.yaml` for organizational policies. Agentlint can fill this gap today.

**New config surface:**
```yaml
# .claude/governance.yaml (or agentlint governance section)
governance:
  file_scope:
    allow: ["src/**", "tests/**", "docs/**"]
    deny: ["*.env", "credentials/**", ".github/workflows/**"]
  tool_restrictions:
    deny: ["Bash"]  # or limit to specific commands
  branch_policy:
    protected: ["main", "master", "release/*"]
    require_branch: true  # Must create feature branch before coding
  budget:
    max_tool_invocations: 200
    max_content_bytes: 500000
  audit:
    log_file: ".agentlint/audit.jsonl"
    log_events: ["PreToolUse", "PostToolUse"]
```

**Implementation:**
- New `governance.py` module — config loader for governance YAML
- New rules: `file-scope-enforcement`, `tool-restriction`, `branch-policy`
- Integrates with existing config system (governance overrides agentlint.yml where they overlap)

---

### Quality Pack (Size: M)

New pack for code quality rules beyond security.

**Rules:**

#### `no-error-handling-removal`
- **Event:** PreToolUse | **Severity:** WARNING
- Detects removal of try/except, null checks, `.catch()`, ErrorBoundary components
- Requires file content caching (see below) for diff-based detection
- **Fallback for v0.4.0:** Pattern-based detection in new content (try blocks replaced with bare code)

#### `no-dead-imports`
- **Event:** PostToolUse | **Severity:** INFO
- Detects imports that are not used in the file after Write/Edit
- Python: `import foo` where `foo` never appears in body
- JavaScript/TypeScript: `import { X }` where `X` never appears

#### `run-linter` — Wrap Existing Project Linters
- **Event:** PostToolUse | **Severity:** WARNING
- After every Write/Edit, run the project's configured linter on the changed file
- **Config:**
  ```yaml
  run-linter:
    commands:
      python: "ruff check {file}"
      typescript: "npx eslint {file}"
      go: "golangci-lint run {file}"
    timeout: 10  # seconds
  ```
- **Architecture concern:** Adds subprocess execution inside rule evaluation. Needs:
  - Timeout parameter on engine or rule level
  - Sandboxing — linter must not modify files
  - Caching — don't re-run on unchanged files
- **This is the most complex feature in the entire roadmap**

---

### File Content Caching (Size: M)

**Engine change:** Cache pre-edit file content during PreToolUse to make it available during PostToolUse.

**How it works:**
1. During PreToolUse for Write/Edit, read the current file and store in session state
2. During PostToolUse, compare cached content with new content
3. Enables diff-based rules: test weakening v2, error handling removal, assertion change detection

**Session state addition:**
```python
session_state["file_cache"] = {
    "path/to/file.py": "original content before edit..."
}
```

---

### Cost / Token Budget Monitoring (Size: M)

**Challenge:** Claude Code doesn't expose token usage in hook payloads.

**Pragmatic approach (proxy metrics):**
- Track total content size written/edited (sum of `tool_input.content` lengths)
- Track total Bash command lengths
- Track number of tool invocations per type
- Report at Stop with a "session activity estimate"

**Config:**
```yaml
rules:
  token-budget:
    max_tool_invocations: 200
    max_content_bytes: 500000
    warn_at_percent: 80
```

**Better approach (if Claude Code exposes it later):** Read `CLAUDE_SESSION_COST` env var.

---

### v0.4.0 Summary

| Feature | Size | Engine Change? | Plugin Change? |
|---------|------|---------------|----------------|
| New hook events | L | Yes (enum, CLI routing) | Yes (hooks.json) |
| Governance config | L | Yes (config loader) | No |
| Quality pack (3 rules) | M | No (pack only) | No |
| Linter wrapping | L | Yes (subprocess, timeout) | No |
| File content caching | M | Yes (session state) | No |
| Token budget | M | No (session state) | No |

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

## v0.6.0+ Backlog

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
