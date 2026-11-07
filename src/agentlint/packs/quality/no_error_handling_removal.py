"""Rule: warn when error handling patterns are removed from code."""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_FILE_TOOLS = {"Write", "Edit"}

# JS/TS error handling patterns
_JS_TRY_RE = re.compile(r"\btry\s*\{", re.MULTILINE)
_JS_CATCH_RE = re.compile(r"\.catch\s*\(", re.MULTILINE)
_JS_ERROR_BOUNDARY_RE = re.compile(r"<ErrorBoundary\b", re.MULTILINE)

_TEST_PATTERNS = re.compile(r"test[_/]|spec[_/]|_test\.|\.test\.|\.spec\.", re.IGNORECASE)


def _count_error_handling(content: str, file_path: str) -> int:
    """Count error handling patterns in content."""
    count = 0
    if file_path.endswith(".py"):
        return len(_python_guards(content))
    else:
        count += len(_JS_TRY_RE.findall(content))
        count += len(_JS_CATCH_RE.findall(content))
        count += len(_JS_ERROR_BOUNDARY_RE.findall(content))
    return count


def _python_guards(content: str) -> list[ast.AST]:
    """Only executable handlers and None guards, never comments or strings."""
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError, RecursionError):
        return []
    return [
        node
        for node in ast.walk(tree)
        if (
            isinstance(node, ast.Try | ast.TryStar)
            and (node.handlers or node.finalbody)
            or isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and any(
                isinstance(value, ast.Constant) and value.value is None
                for value in [node.test.left, *node.test.comparators]
            )
            and any(isinstance(op, ast.Is | ast.IsNot) for op in node.test.ops)
        )
    ]


def _bindings(tree: ast.AST) -> Counter:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
            names.append(node.id)
        elif isinstance(node, ast.arg):
            names.append(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.append(node.name)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            names.extend(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and node.name:
            names.append(node.name)
    return Counter(names)


def _verified_relocation(context: RuleContext, before: str, after: str) -> bool:
    """Recognize a direct extraction only from the same inspected patch.

    Require the same guard AST, direct invocation in the original scope, exact
    import target and unchanged argument bindings. A helper-like name alone is
    not evidence that handling survived.
    """
    try:
        old, new = ast.parse(before), ast.parse(after)
        new_bindings = _bindings(new)
        root = Path(context.project_dir).resolve()
        current = (root / (context.file_path or "")).resolve()
        inspected = {Path(path).resolve(): text for path, text in context.related_files.items()}
        helpers = {}
        for stmt in new.body:
            if not isinstance(stmt, ast.ImportFrom) or not stmt.module:
                continue
            base = current.parent
            for _ in range(max(0, stmt.level - 1)):
                base = base.parent
            relative = Path(*stmt.module.split(".")).with_suffix(".py")
            targets = (
                [base / relative] if stmt.level else [root / relative, root / "src" / relative]
            )
            targets = [
                path.resolve()
                for path in targets
                if path.resolve() in inspected and path.resolve().is_relative_to(root)
            ]
            if len(targets) != 1:
                continue
            module = ast.parse(inspected[targets[0]])
            module_bindings = _bindings(module)
            for alias in stmt.names:
                functions = [
                    node
                    for node in module.body
                    if isinstance(node, ast.FunctionDef) and node.name == alias.name
                ]
                if (
                    len(functions) == 1
                    and module_bindings[alias.name] == 1
                    and new_bindings[alias.asname or alias.name] == 1
                ):
                    helpers[alias.asname or alias.name] = functions[0]

        def scopes(tree):
            return [tree, *(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))]

        for guard in _python_guards(before):
            # A helper has its own frame: exits and local bindings cannot be
            # moved there without changing the caller's behavior.
            if any(
                isinstance(node, ast.Return | ast.Break | ast.Continue | ast.Yield | ast.YieldFrom)
                or isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Store | ast.Del)
                for node in ast.walk(guard)
            ):
                return False
            guarded_names = {node.id for node in ast.walk(guard) if isinstance(node, ast.Name)}
            old_scopes = [
                scope
                for scope in scopes(old)
                if any(node.lineno == guard.lineno for node in scope.body)
            ]
            if len(old_scopes) != 1:
                return False
            name = getattr(old_scopes[0], "name", None)
            new_scopes = [scope for scope in scopes(new) if getattr(scope, "name", None) == name]
            if len(new_scopes) != 1:
                return False
            relocated = False
            reachable = []
            for statement in new_scopes[0].body:
                reachable.append(statement)
                if any(
                    isinstance(node, ast.Return | ast.Raise | ast.Break | ast.Continue)
                    for node in ast.walk(statement)
                ):
                    break
            for index, stmt in enumerate(reachable):
                call = getattr(stmt, "value", None)
                if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
                    continue
                if any(
                    isinstance(node, ast.Name) and node.id in guarded_names
                    for preceding in reachable[:index]
                    for node in ast.walk(preceding)
                ):
                    continue
                helper = helpers.get(call.func.id)
                if helper is None or helper.decorator_list or call.keywords:
                    continue
                params = helper.args.posonlyargs + helper.args.args
                if (
                    helper.args.vararg
                    or helper.args.kwarg
                    or helper.args.kwonlyargs
                    or len(params) != len(call.args)
                    or any(
                        not isinstance(arg, ast.Name) or arg.id != param.arg
                        for arg, param in zip(call.args, params, strict=True)
                    )
                ):
                    continue
                body = helper.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    body = body[1:]
                if body and ast.dump(body[0]) == ast.dump(guard):
                    relocated = True
                    break
            if not relocated:
                return False
        return True
    except (SyntaxError, ValueError, RecursionError, OSError):
        return False


def _is_code_file(path: str) -> bool:
    return any(path.endswith(ext) for ext in (".py", ".js", ".jsx", ".ts", ".tsx"))


class NoErrorHandlingRemoval(Rule):
    """Warn when error handling is removed from code."""

    id = "no-error-handling-removal"
    description = "Warns when error handling patterns (try/except, .catch) are removed"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "quality"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _FILE_TOOLS:
            return []

        file_path = context.file_path or ""
        if not file_path or not _is_code_file(file_path):
            return []

        # Skip test files
        if _TEST_PATTERNS.search(context.relative_file_path or file_path):
            return []

        new_content = context.file_content
        if new_content is None:
            new_content = context.tool_input.get("content", context.tool_input.get("new_string"))
        if new_content is None:
            return []

        old_content = context.file_content_before
        if not old_content:
            return []

        rule_config = context.config.get(self.id, {})
        if not rule_config.get("enabled", True):
            return []

        old_count = _count_error_handling(old_content, file_path)
        new_count = _count_error_handling(new_content, file_path)

        if old_count > 0 and new_count == 0:
            if (
                file_path.endswith(".py")
                and context.related_files
                and _verified_relocation(context, old_content, new_content)
            ):
                return []
            if file_path.endswith(".py"):
                node = _python_guards(old_content)[0]
                if isinstance(node, ast.Try | ast.TryStar) and node.handlers:
                    node = node.handlers[0]
                line = node.lineno
                evidence = old_content.splitlines()[line - 1].strip()
                kind = "guard" if isinstance(node, ast.If) else "handler"
            else:
                match = next(
                    (
                        pattern.search(old_content)
                        for pattern in (
                            _JS_TRY_RE,
                            _JS_CATCH_RE,
                            _JS_ERROR_BOUNDARY_RE,
                        )
                        if pattern.search(old_content)
                    ),
                    None,
                )
                line = old_content.count("\n", 0, match.start()) + 1 if match else None
                evidence = old_content.splitlines()[line - 1].strip() if line else ""
                kind = "handler"
            return [
                Violation(
                    rule_id=self.id,
                    message=f"Local {kind} removed or relocated: {evidence}",
                    severity=self.severity,
                    file_path=file_path,
                    line=line,
                    suggestion=(
                        "Verify equivalent handling in the called helper. This per-file "
                        "check cannot establish removal across files; preserve the guard "
                        "or confirm its relocation."
                    ),
                )
            ]

        return []
