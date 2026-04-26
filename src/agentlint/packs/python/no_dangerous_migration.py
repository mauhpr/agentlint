"""Rule: detect risky Alembic migration operations.

Operations are evaluated in the context of their enclosing function — most
``op.drop_*`` calls inside ``def downgrade()`` are the intentional inverse
of the upgrade and should not be flagged. The rule still warns when an
``upgrade()`` performs an irreversible operation without a corresponding
``downgrade()`` body, but does not double-fire on the downgrade itself.
"""
from __future__ import annotations

import ast
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


def _extract_function_source(content: str, name: str) -> str | None:
    """Return the source segment of a top-level function with ``name``.

    Uses ``ast`` so comments, string literals and indented defs nested
    inside other constructs can't fool the matcher. Returns ``None`` when
    the function is not found OR the file fails to parse — in that case
    the caller should fall back to whole-file scanning so a malformed
    migration still gets best-effort checks rather than crashing.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            segment = ast.get_source_segment(content, node)
            return segment if segment is not None else ""
    return None


def _function_line_range(content: str, name: str) -> tuple[int, int] | None:
    """Return (start_line, end_line) inclusive of a top-level function.

    Both line numbers are 1-based to match the line counting we use when
    reporting violations. Returns ``None`` when parsing fails or the
    function is missing — callers should treat that as "unknown scope"
    and fall back to permissive behaviour.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            end = getattr(node, "end_lineno", None) or node.lineno
            return node.lineno, end
    return None


def _is_line_in_function(content: str, char_offset: int, name: str) -> bool:
    """Return True when the character offset falls within a function's body.

    When we can't determine the function range (parse error / function
    missing), assume True — that preserves the historical "whole-file"
    behaviour so malformed migrations still get checked.
    """
    rng = _function_line_range(content, name)
    if rng is None:
        return True
    line_num = content[:char_offset].count("\n") + 1
    start, end = rng
    return start <= line_num <= end


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

        # Scope-aware extraction. If parsing fails or functions aren't found,
        # the upgrade/downgrade sources fall back to the whole file, preserving
        # legacy whole-file behaviour for malformed migrations.
        upgrade_src = _extract_function_source(content, "upgrade")
        downgrade_src = _extract_function_source(content, "downgrade")
        if upgrade_src is None and downgrade_src is None:
            upgrade_src = content
            downgrade_src = ""
        else:
            upgrade_src = upgrade_src or ""
            downgrade_src = downgrade_src or ""

        # drop_table in upgrade is irreversible unless downgrade re-creates the table.
        # drop_table in downgrade is the expected inverse of an upgrade create_table —
        # it's not a forward-direction destructive op, so we don't fire on it.
        if _DROP_TABLE_RE.search(upgrade_src) and not _CREATE_TABLE_RE.search(downgrade_src):
            for match in _DROP_TABLE_RE.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                # Only flag occurrences that fall within the upgrade body.
                # We re-scan content to keep accurate line numbers.
                if _is_line_in_function(content, match.start(), "upgrade"):
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message="op.drop_table() in upgrade() without op.create_table() in downgrade()",
                            severity=self.severity,
                            file_path=file_path,
                            line=line_num,
                            suggestion="Add a create_table in the downgrade() to make migration reversible.",
                        )
                    )

        # drop_column — only flag when it sits in upgrade(). drop_column in
        # downgrade() is the expected inverse of an upgrade add_column and
        # tests need it for state-reset workflows.
        for match in _DROP_COLUMN_RE.finditer(content):
            if not _is_line_in_function(content, match.start(), "upgrade"):
                continue
            line_num = content[:match.start()].count("\n") + 1
            violations.append(
                Violation(
                    rule_id=self.id,
                    message="op.drop_column() in upgrade() is destructive and hard to reverse",
                    severity=self.severity,
                    file_path=file_path,
                    line=line_num,
                    suggestion="Consider a two-step migration: deprecate then drop.",
                )
            )

        # alter_column with nullable=False — only enforce in upgrade().
        for match in _ALTER_NULLABLE_RE.finditer(content):
            if not _is_line_in_function(content, match.start(), "upgrade"):
                continue
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

        # DateTime without timezone — file-wide check (it's a schema concern,
        # not a direction concern).
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
