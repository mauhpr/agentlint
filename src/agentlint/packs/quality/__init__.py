"""Quality rule pack — code quality and best practices."""
from agentlint.packs.quality.commit_message_format import CommitMessageFormat
from agentlint.packs.quality.no_dead_imports import NoDeadImports
from agentlint.packs.quality.no_error_handling_removal import NoErrorHandlingRemoval
from agentlint.packs.quality.self_review_prompt import SelfReviewPrompt

RULES = [
    # PreToolUse
    CommitMessageFormat(),
    NoErrorHandlingRemoval(),
    # PostToolUse
    NoDeadImports(),
    # Stop
    SelfReviewPrompt(),
]
