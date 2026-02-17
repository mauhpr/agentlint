#!/bin/bash
# AgentLint PreToolUse hook
# Pipes Claude Code tool input to agentlint for validation
cat | agentlint check --event PreToolUse --project-dir "$CLAUDE_PROJECT_DIR"
exit $?
