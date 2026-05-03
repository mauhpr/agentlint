# Setup Guide: Gemini CLI (Google)

AgentLint supports Gemini CLI via native hooks in `.gemini/settings.json`.

## Installation

```bash
agentlint setup gemini
```

This creates `.gemini/settings.json` in your project root with hooks for:

- `BeforeTool` — blocks secrets, destructive commands, etc.
- `AfterTool` — checks file quality after edits
- `BeforeAgent` — prompt-level rule evaluation
- `AfterAgent` — session-end checks
- `SessionStart` — session initialization
- `PreCompress` — compact context warnings

## Hook Format

Gemini CLI uses a unique JSON-based hook protocol:

- **Exit 0** — success; JSON output parsed
- **Exit 2** — can also block for some events

Blocking output (for `BeforeTool`, `BeforeAgent`, `BeforeModel`):
```json
{
  "decision": "deny",
  "reason": "[no-secrets] Possible secret token detected",
  "systemMessage": "AgentLint blocked this action."
}
```

Advisory output (for `AfterTool`, `AfterAgent`, `AfterModel`):
```json
{
  "hookSpecificOutput": {
    "hookEventName": "AfterTool",
    "additionalContext": "[max-file-size] File exceeds limit"
  }
}
```

## Global Installation

```bash
agentlint setup gemini --global
```

Installs to `~/.gemini/settings.json` (affects all projects).

## Uninstall

```bash
agentlint uninstall gemini
```

Removes only AgentLint hooks; preserves any other custom hooks you have configured.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `GEMINI_PROJECT_DIR` | Project directory override |
| `GEMINI_SESSION_ID` | Session ID for state tracking |
| `AGENTLINT_PROJECT_DIR` | Generic project directory (takes precedence) |
| `AGENTLINT_SESSION_ID` | Generic session ID (takes precedence) |

## Troubleshooting

**Hooks not firing?**
- Verify `.gemini/settings.json` exists and contains a `"hooks"` key
- Gemini uses a different event taxonomy (`BeforeTool`/`AfterTool` instead of `PreToolUse`/`PostToolUse`)
- Run `agentlint doctor` to diagnose installation issues
