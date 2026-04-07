---
name: lint-status
description: Show AgentLint status — active rules, violations this session
---

Run `agentlint status --project-dir "$CLAUDE_PROJECT_DIR"` and display:
1. Which rule packs are active (including custom packs)
2. How many rules are running (64 built-in across 8 packs, plus any custom rules)
3. Current severity mode
4. Session activity: tool calls tracked, token budget usage
5. Any violations found this session

If the user reports problems, suggest running `agentlint doctor --project-dir "$CLAUDE_PROJECT_DIR"` to diagnose misconfigurations.
