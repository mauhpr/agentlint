"""Rule: detect SQL injection via string interpolation in Python files."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}

_SQL_KEYWORDS = {"SELECT", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE"}
_SQL_ALTERNATION = "|".join(_SQL_KEYWORDS)

# f-string SQL: f"SELECT ... {
_FSTRING_SQL_RE = re.compile(
    r"""f['"](""" + _SQL_ALTERNATION + r""")\b""",
    re.IGNORECASE,
)

# .format() SQL: "SELECT ...".format(
_FORMAT_SQL_RE = re.compile(
    r"""['"](?:""" + _SQL_ALTERNATION + r""")\b[^'"]*['"]\.format\s*\(""",
    re.IGNORECASE,
)

# String concat: "SELECT " +
_CONCAT_SQL_RE = re.compile(
    r"""['"](?:""" + _SQL_ALTERNATION + r""")\b[^'"]*['"]\s*\+""",
    re.IGNORECASE,
)

# % operator: "SELECT ... %s" %
_PERCENT_SQL_RE = re.compile(
    r"""['"](?:""" + _SQL_ALTERNATION + r""")\b[^'"]*%[sd][^'"]*['"]\s*%""",
    re.IGNORECASE,
)


def _is_comment_line(line: str) -> bool:
    return line.lstrip().startswith("#")


def _is_test_or_sql_file(file_path: str | None) -> bool:
    if not file_path:
        return False
    lower = file_path.lower()
    return lower.endswith(".sql") or "/test" in lower or "test_" in lower.split("/")[-1]


class NoSqlInjection(Rule):
    """Detect SQL injection via string interpolation in Python files."""

    id = "no-sql-injection"
    description = "Prevents SQL injection via string interpolation"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "python"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []

        file_path = context.file_path
        if not file_path or not file_path.endswith(".py"):
            return []

        if _is_test_or_sql_file(file_path):
            return []

        content = context.tool_input.get("content", "")
        if not content:
            return []

        extra_keywords = context.config.get("extra_keywords", [])

        violations: list[Violation] = []
        patterns = [
            (_FSTRING_SQL_RE, "f-string SQL interpolation"),
            (_FORMAT_SQL_RE, ".format() SQL interpolation"),
            (_CONCAT_SQL_RE, "string concatenation in SQL"),
            (_PERCENT_SQL_RE, "% operator SQL interpolation"),
        ]

        # Build extra patterns if configured
        if extra_keywords:
            extra_joined = "|".join(re.escape(k) for k in extra_keywords)
            patterns.append((
                re.compile(r"""f['"](?:""" + extra_joined + r""")\b""", re.IGNORECASE),
                "f-string interpolation with custom keyword",
            ))

        for line_num, line in enumerate(content.splitlines(), start=1):
            if _is_comment_line(line):
                continue
            for pattern, desc in patterns:
                if pattern.search(line):
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=f"Possible SQL injection: {desc}",
                            severity=self.severity,
                            file_path=file_path,
                            line=line_num,
                            suggestion="Use parameterized queries instead of string interpolation.",
                        )
                    )
                    break  # one violation per line

        return violations
