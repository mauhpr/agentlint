"""Quality rule pack — code quality and best practices."""
from agentlint.packs.quality.commit_message_format import CommitMessageFormat
from agentlint.packs.quality.naming_conventions import NamingConventions
from agentlint.packs.quality.no_dead_imports import NoDeadImports
from agentlint.packs.quality.no_error_handling_removal import NoErrorHandlingRemoval
from agentlint.packs.quality.no_file_creation_sprawl import NoFileCreationSprawl
from agentlint.packs.quality.no_large_diff import NoLargeDiff
from agentlint.packs.quality.self_review_prompt import SelfReviewPrompt

RULES = [
    # PreToolUse
    CommitMessageFormat(),
    NamingConventions(),
    NoErrorHandlingRemoval(),
    # PostToolUse
    NoDeadImports(),
    NoLargeDiff(),
    NoFileCreationSprawl(),
    # Stop
    SelfReviewPrompt(),
]
