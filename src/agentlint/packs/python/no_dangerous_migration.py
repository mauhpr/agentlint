"""Rule: detect risky Alembic migration operations."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}

_DEFAULT_MIGRATION_MARKERS = {"migration", "alembic", "versions"}

_DROP_TABLE_RE = re.compile(r"\bop\.drop_table\s*\(")
_CREATE_TABLE_RE = re.compile(r"\bop\.create_table\s*\(")
_DROP_COLUMN_RE = re.compile(r"\bop\.drop_column\s*\(")
_ALTER_NULLABLE_RE = re.compile(r"\bop\.alter_column\s*\([^)]*nullable\s*=\s*False", re.DOTALL)
_DATETIME_NO_TZ_RE = re.compile(r"\bsa\.DateTime\b(?![^)]*timezone\s*=\s*True)")


def _is_migration_file(file_path: str, migration_paths: list[str]) -> bool:
    lower = file_path.lower()
    markers = set(migration_paths) if migration_paths else _DEFAULT_MIGRATION_MARKERS
    return any(marker in lower for marker in markers)


class NoDangerousMigration(Rule):
    """Detect risky Alembic migration operations."""

    id = "no-dangerous-migration"
    description = "Warns about dangerous database migration operations"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "python"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []

        file_path = context.file_path
        if not file_path or not file_path.endswith(".py"):
            return []

        migration_paths = context.config.get("migration_paths", [])
        if not _is_migration_file(file_path, migration_paths):
            return []

        content = context.tool_input.get("content", "")
        if not content:
            return []

        require_timezone = context.config.get("require_timezone", True)
        violations: list[Violation] = []

        # drop_table without create_table (irreversible)
        if _DROP_TABLE_RE.search(content) and not _CREATE_TABLE_RE.search(content):
            for match in _DROP_TABLE_RE.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="op.drop_table() without corresponding op.create_table()",
                        severity=self.severity,
                        file_path=file_path,
                        line=line_num,
                        suggestion="Add a create_table in the downgrade() to make migration reversible.",
                    )
                )

        # drop_column
        for match in _DROP_COLUMN_RE.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="op.drop_column() is a destructive, hard-to-reverse operation",
                    severity=self.severity,
                    file_path=file_path,
                    line=line_num,
                    suggestion="Consider a two-step migration: deprecate then drop.",
                )
            )

        # alter_column with nullable=False
        for match in _ALTER_NULLABLE_RE.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="op.alter_column() with nullable=False may fail on existing NULLs",
                    severity=self.severity,
                    file_path=file_path,
                    line=line_num,
                    suggestion="Add a data migration to fill NULLs before setting nullable=False.",
                )
            )

        # DateTime without timezone
        if require_timezone:
            for match in _DATETIME_NO_TZ_RE.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="sa.DateTime without timezone=True",
                        severity=self.severity,
                        file_path=file_path,
                        line=line_num,
                        suggestion="Use sa.DateTime(timezone=True) to store timezone-aware datetimes.",
                    )
                )

        return violations
