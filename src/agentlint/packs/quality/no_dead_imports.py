"""Rule: detect unused imports in written/edited files."""

from __future__ import annotations

import ast
import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_FILE_TOOLS = {"Write", "Edit"}

# JS/TS imports: import { X, Y } from '...', import X from '...'
_JS_IMPORT_RE = re.compile(
    r"""^\s*import\s+(?:\{([^}]+)\}|(\w+))\s+from\s+['"]""",
    re.MULTILINE,
)

# Files where unused imports are expected (re-exports)
_IGNORE_BASENAMES = {"__init__.py", "index.ts", "index.js", "index.tsx", "index.jsx"}


def _python_import_names(tree: ast.AST) -> list[str]:
    """Extract bound names, including aliases and multiline imports."""
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
        for alias in node.names:
            if alias.name != "*":
                names.append(alias.asname or alias.name.split(".")[0])
    return names


def _extract_js_names(content: str) -> list[str]:
    """Extract imported names from JS/TS import statements."""
    names: list[str] = []
    for match in _JS_IMPORT_RE.finditer(content):
        braces = match.group(1)
        default = match.group(2)
        if braces:
            for item in braces.split(","):
                item = item.strip()
                if not item:
                    continue
                if " as " in item:
                    names.append(item.split(" as ")[-1].strip())
                else:
                    names.append(item.strip())
        if default:
            names.append(default)
    return names


def _is_python_file(path: str) -> bool:
    return path.endswith(".py")


def _is_js_ts_file(path: str) -> bool:
    return any(path.endswith(ext) for ext in (".js", ".jsx", ".ts", ".tsx"))


def _find_unused(file_path: str, content: str) -> list[str]:
    """Find unused import names in file content. Returns list of unused names."""
    if _is_python_file(file_path):
        try:
            tree = ast.parse(content)
        except (SyntaxError, ValueError, RecursionError):
            return []
        names = _python_import_names(tree)
        used = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                used.update(re.findall(r"\b[A-Za-z_]\w*\b", node.value))
        return [name for name in names if not name.startswith("_") and name not in used]
    elif _is_js_ts_file(file_path):
        names = _extract_js_names(content)
    else:
        return []

    # Strip import lines to get the "body" for reference checking
    body_lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("import ", "from ")) and "import" in stripped:
            continue
        body_lines.append(line)
    body = "\n".join(body_lines)

    unused = []
    for name in names:
        if not name or name.startswith("_"):
            continue
        if not re.search(rf"\b{re.escape(name)}\b", body):
            unused.append(name)
    return unused


class NoDeadImports(Rule):
    """Detect unused imports in written/edited files.

    Uses a grace period to avoid false positives during multi-edit workflows.
    When imports are added first and used in a subsequent edit, the first edit
    gets a free pass. The violation only fires if the imports are still unused
    on the next edit to the same file.
    """

    id = "no-dead-imports"
    description = "Detects unused imports in Python and JS/TS files"
    severity = Severity.INFO
    events = [HookEvent.POST_TOOL_USE]
    pack = "quality"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _FILE_TOOLS:
            return []

        file_path = context.file_path or ""
        content = context.file_content
        if not file_path or not content:
            return []

        rule_config = context.config.get(self.id, {})
        ignore_files = set(rule_config.get("ignore_files", _IGNORE_BASENAMES))
        grace = rule_config.get("grace_period", True)

        # Check if this file should be ignored
        import os

        basename = os.path.basename(file_path)
        if basename in ignore_files:
            return []

        unused = _find_unused(file_path, content)

        # Grace period: defer first detection, fire on second consecutive
        if grace and context.session_state is not None:
            pending = context.session_state.setdefault("_dead_imports_pending", {})
            prev_unused = pending.get(file_path)

            if not unused:
                # Imports are now used — clear any pending
                pending.pop(file_path, None)
                return []

            if prev_unused is None:
                # First time seeing unused imports in this file — defer
                pending[file_path] = unused
                return []

            # Second+ edit and still unused — fire and clear
            pending.pop(file_path, None)

        if not unused:
            return []

        return [
            Violation(
                rule_id=self.id,
                message=f"Potentially unused import{'s' if len(unused) > 1 else ''}: {', '.join(unused)}",
                severity=self.severity,
                file_path=file_path,
                suggestion="Remove unused imports or verify they are needed for side effects.",
            )
        ]
