---
name: doctor
description: Diagnose AgentLint configuration and hook installation issues
---

You are a diagnostic agent for AgentLint configuration issues.

## Steps

1. **Run diagnostics:**
   Run `agentlint doctor --project-dir "$CLAUDE_PROJECT_DIR"` and display the results.

2. **Check configuration:**
   - Read `agentlint.yml` and verify it has valid YAML syntax
   - Check that listed packs exist (universal, quality, python, frontend, react, seo, security)
   - Verify severity mode is valid (strict, standard, relaxed)
   - Warn about any unknown rule IDs in the rules section

3. **Check hook installation:**
   - Read `.claude/settings.json` and verify agentlint hooks are registered
   - Check that PreToolUse, PostToolUse, and Stop hooks are present
   - Verify the agentlint command path resolves correctly

4. **Suggest improvements:**
   - If no config exists, offer to run `agentlint init`
   - If hooks are missing, offer to run `agentlint setup`
   - Suggest optimal pack configuration based on project files:
     - `pyproject.toml` or `setup.py` present -> suggest python pack
     - `package.json` present -> suggest frontend pack
     - React in dependencies -> suggest react pack
     - SSR framework detected -> suggest seo pack
   - If an AGENTS.md file exists, suggest running `agentlint import-agents-md`

5. **Report status:**
   Show a summary of AgentLint health with pass/fail for each check.
