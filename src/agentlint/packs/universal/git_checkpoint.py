"""Rule: create a git safety checkpoint before destructive operations."""
from __future__ import annotations

import re
import time

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

_CHECKPOINT_PREFIX = "agentlint-checkpoint"

# Default destructive command patterns that trigger checkpointing.
_DEFAULT_TRIGGERS = [
    r"\brm\s+-[^\s]*r[^\s]*f|\brm\s+-[^\s]*f[^\s]*r",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+checkout\s+\.(?:\s|$)",
    r"\bgit\s+clean\s+-fd\b",
    r"\bDROP\s+TABLE\b",
    r"\bDROP\s+DATABASE\b",
]

_DEFAULT_TRIGGER_RES = [re.compile(p, re.IGNORECASE) for p in _DEFAULT_TRIGGERS]


class GitCheckpoint(Rule):
    """Create a git safety checkpoint before destructive operations.

    Automatically runs ``git stash push`` when a destructive command is detected,
    preserving uncommitted work. Disabled by default — opt in via config.

    Config options:
        enabled: false (default)
        cleanup_hours: 24
        triggers: [list of regex patterns]
    """

    id = "git-checkpoint"
    description = "Creates a git safety checkpoint before destructive operations"
    severity = Severity.INFO
    events = [HookEvent.PRE_TOOL_USE, HookEvent.STOP]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.event == HookEvent.STOP:
            return self._cleanup(context)
        return self._checkpoint(context)

    def _checkpoint(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        rule_config = context.config.get(self.id, {})
        trigger_patterns = self._get_trigger_patterns(rule_config)

        if not any(p.search(command) for p in trigger_patterns):
            return []

        # Only checkpoint if in a git repo with uncommitted changes.
        from agentlint.utils.git import git_has_changes, git_stash_push, is_git_repo

        if not is_git_repo(context.project_dir):
            return []
        if not git_has_changes(context.project_dir):
            return []

        timestamp = int(time.time())
        message = f"{_CHECKPOINT_PREFIX}-{timestamp}"
        if git_stash_push(context.project_dir, message):
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Created git checkpoint before destructive operation. Use `git stash pop` to recover if needed.",
                    severity=self.severity,
                    suggestion=f"Checkpoint saved as: {message}",
                )
            ]

        return []

    def _cleanup(self, context: RuleContext) -> list[Violation]:
        """Clean up old checkpoints on Stop event."""
        rule_config = context.config.get(self.id, {})
        cleanup_hours = rule_config.get("cleanup_hours", 24)

        from agentlint.utils.git import git_clean_stashes, is_git_repo

        if not is_git_repo(context.project_dir):
            return []

        removed = git_clean_stashes(context.project_dir, _CHECKPOINT_PREFIX, cleanup_hours)
        if removed > 0:
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Cleaned up {removed} old checkpoint(s) (older than {cleanup_hours}h).",
                    severity=Severity.INFO,
                )
            ]
        return []

    @staticmethod
    def _get_trigger_patterns(rule_config: dict) -> list[re.Pattern]:
        custom_triggers = rule_config.get("triggers")
        if custom_triggers:
            return [re.compile(t, re.IGNORECASE) for t in custom_triggers]
        return _DEFAULT_TRIGGER_RES
