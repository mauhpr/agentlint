"""Python rule pack — security and code quality rules for Python projects."""
from agentlint.packs.python.no_sql_injection import NoSqlInjection
from agentlint.packs.python.no_bare_except import NoBareExcept
from agentlint.packs.python.no_unsafe_shell import NoUnsafeShell
from agentlint.packs.python.no_dangerous_migration import NoDangerousMigration
from agentlint.packs.python.no_wildcard_import import NoWildcardImport
from agentlint.packs.python.no_unnecessary_async import NoUnnecessaryAsync

RULES = [
    # PreToolUse
    NoSqlInjection(),
    NoBareExcept(),
    NoUnsafeShell(),
    NoDangerousMigration(),
    NoWildcardImport(),
    # PostToolUse
    NoUnnecessaryAsync(),
]
