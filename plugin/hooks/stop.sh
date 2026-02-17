#!/bin/bash
# AgentLint Stop hook
# Generates session quality report
cat | agentlint report --project-dir "$CLAUDE_PROJECT_DIR"
exit $?
