"""Rule: useQuery/useMutation without loading/error state handling."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_WRITE_TOOLS = {"Write", "Edit"}
_REACT_EXTENSIONS = {".tsx", ".jsx"}

_DEFAULT_QUERY_HOOKS = {"useQuery", "useSuspenseQuery"}
_MUTATION_HOOK = "useMutation"

_LOADING_STATES = {"isLoading", "isPending", "isFetching"}
_ERROR_STATES = {"isError", "error"}


def _is_react_file(file_path: str | None) -> bool:
    if not file_path:
        return False
    return any(file_path.endswith(ext) for ext in _REACT_EXTENSIONS)


class ReactQueryLoadingState(Rule):
    """useQuery without loading/error state handling."""

    id = "react-query-loading-state"
    description = "Ensures useQuery/useMutation results handle loading and error states"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "react"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _WRITE_TOOLS:
            return []
        if not _is_react_file(context.file_path):
            return []

        content = context.tool_input.get("content", "")
        if not content:
            return []

        hooks = set(context.config.get("hooks", [])) or _DEFAULT_QUERY_HOOKS
        violations: list[Violation] = []

        # Check query hooks
        for hook in hooks:
            pattern = re.compile(r"\b" + re.escape(hook) + r"\s*\(")
            for match in pattern.finditer(content):
                line_num = content[:match.start()].count("\n") + 1
                has_loading = any(s in content for s in _LOADING_STATES)
                has_error = any(s in content for s in _ERROR_STATES)
                if not has_loading or not has_error:
                    missing = []
                    if not has_loading:
                        missing.append("loading")
                    if not has_error:
                        missing.append("error")
                    violations.append(
                        Violation(
                            rule_id=self.id,
                            message=f"{hook}() without {'/'.join(missing)} state handling",
                            severity=self.severity,
                            file_path=context.file_path,
                            line=line_num,
                            suggestion=f"Destructure isLoading/isPending and isError from {hook}().",
                        )
                    )

        # Check useMutation
        mutation_pattern = re.compile(r"\b" + re.escape(_MUTATION_HOOK) + r"\s*\(")
        for match in mutation_pattern.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            if "isPending" not in content:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message="useMutation() without isPending state handling",
                        severity=self.severity,
                        file_path=context.file_path,
                        line=line_num,
                        suggestion="Use isPending from useMutation() to disable submit buttons.",
                    )
                )

        return violations
