#!/bin/bash
# AgentLint PostToolUse hook
# Validates code after write/edit operations
cat | agentlint check --event PostToolUse --project-dir "$CLAUDE_PROJECT_DIR"
exit $?
