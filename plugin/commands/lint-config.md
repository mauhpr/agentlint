---
name: lint-config
description: Show or edit AgentLint configuration
---

Read the `agentlint.yml` file in the project root and display:
1. Current severity mode (standard/strict/relaxed)
2. Active packs (built-in and custom)
3. Rule overrides
4. Custom rules directory and custom packs
5. CLI integration commands (if configured)

If the user wants to change settings, edit the agentlint.yml file.

Notes:
- The `quality` pack is always active alongside `universal`.
- The `security` and `autopilot` packs are opt-in.
- Custom packs activate when listed in `packs:` and `custom_rules_dir` is set.
- CLI integration runs external tools (linters, scanners) on PostToolUse.
- Use `agentlint list-rules` to see all rules, or `agentlint list-rules --pack <name>` to filter.
- Run `agentlint doctor` to diagnose misconfigurations.
