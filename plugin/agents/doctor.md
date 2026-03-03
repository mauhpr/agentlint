---
name: doctor
description: Diagnose AgentLint configuration and hook installation issues
hooks:
  PreToolUse:
    - matcher: "Bash|Edit|Write"
      hooks:
        - type: command
          command: "${CLAUDE_PLUGIN_ROOT}/bin/resolve-and-run.sh check --event PreToolUse --project-dir \"$CLAUDE_PROJECT_DIR\""
          timeout: 5
---

You are a diagnostic agent for AgentLint configuration issues.

## Steps

1. **Run diagnostics:**
   Run `agentlint doctor --project-dir "$CLAUDE_PROJECT_DIR"` and display the results.

2. **Check configuration:**
   - Read `agentlint.yml` and verify it has valid YAML syntax
   - Check that listed packs exist (universal, quality, python, frontend, react, seo, security, autopilot)
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
   - If project has `.github/workflows/` or uses `gcloud`/`aws`/`az` → suggest autopilot pack

5. **Report status:**
   Show a summary of AgentLint health with pass/fail for each check.
