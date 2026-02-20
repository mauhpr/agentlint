"""Rule: detect async def without await in the body."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}

_ASYNC_DEF_RE = re.compile(r"^(\s*)async\s+def\s+(\w+)\s*\(", re.MULTILINE)
_AWAIT_RE = re.compile(r"\bawait\b")
_SKIP_DECORATORS = {"property", "override", "abstractmethod"}
_SKIP_BODIES = {"pass", "...", "raise NotImplementedError"}


def _is_test_file(file_path: str) -> bool:
    parts = file_path.lower().split("/")
    basename = parts[-1] if parts else ""
    return basename.startswith("test_") or basename.startswith("conftest") or "/test" in file_path.lower()


class NoUnnecessaryAsync(Rule):
    """Detect async def without any await in the body."""

    id = "no-unnecessary-async"
    description = "Flags async functions that don't use await"
    severity = Severity.INFO
    events = [HookEvent.POST_TOOL_USE]
    pack = "python"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []

        file_path = context.file_path
        if not file_path or not file_path.endswith(".py"):
            return []

        if _is_test_file(file_path):
            return []

        content = context.tool_input.get("content", "")
        if not content:
            return []

        ignore_decorators = set(context.config.get("ignore_decorators", []))
        all_skip_decorators = _SKIP_DECORATORS | ignore_decorators

        violations: list[Violation] = []
        lines = content.splitlines()

        for match in _ASYNC_DEF_RE.finditer(content):
            func_indent = len(match.group(1))
            func_name = match.group(2)
            func_line = content[:match.start()].count("\n")

            # Check decorators above
            decorator_line = func_line - 1
            skip = False
            while decorator_line >= 0:
                dline = lines[decorator_line].strip()
                if dline.startswith("@"):
                    dec_name = dline[1:].split("(")[0].split(".")[-1]
                    if dec_name in all_skip_decorators:
                        skip = True
                        break
                    decorator_line -= 1
                elif dline == "" or dline.startswith("#"):
                    decorator_line -= 1
                else:
                    break

            if skip:
                continue

            # Extract body lines
            body_lines = []
            for subsequent in lines[func_line + 1 :]:
                if not subsequent.strip():
                    body_lines.append(subsequent)
                    continue
                sub_indent = len(subsequent) - len(subsequent.lstrip())
                if sub_indent <= func_indent:
                    break
                body_lines.append(subsequent)

            body_text = "\n".join(body_lines)

            # Skip stubs
            body_stripped = body_text.strip()
            if body_stripped in _SKIP_BODIES:
                continue

            if not _AWAIT_RE.search(body_text):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"async def {func_name}() has no await expression",
                        severity=self.severity,
                        file_path=file_path,
                        line=func_line + 1,
                        suggestion=f"Remove async from {func_name}() or add await expressions.",
                    )
                )

        return violations
