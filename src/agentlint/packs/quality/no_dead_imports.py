"""Rule: detect unused imports in written/edited files."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_FILE_TOOLS = {"Write", "Edit"}

# Python imports: import foo, from foo import bar, from foo import bar, baz
_PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+\S+\s+)?import\s+(.+)", re.MULTILINE)

# JS/TS imports: import { X, Y } from '...', import X from '...'
_JS_IMPORT_RE = re.compile(
    r"""^\s*import\s+(?:\{([^}]+)\}|(\w+))\s+from\s+['"]""",
    re.MULTILINE,
)

# Files where unused imports are expected (re-exports)
_IGNORE_BASENAMES = {"__init__.py", "index.ts", "index.js", "index.tsx", "index.jsx"}


def _extract_python_names(content: str) -> list[str]:
    """Extract imported names from Python import statements."""
    names: list[str] = []
    for match in _PY_IMPORT_RE.finditer(content):
        imported = match.group(1)
        # Handle "from x import a, b as c" → extract "a", "c"
        for item in imported.split(","):
            item = item.strip()
            if not item:
                continue
            if " as " in item:
                names.append(item.split(" as ")[-1].strip())
            else:
                # "import foo.bar" → use "foo"
                names.append(item.split(".")[0].strip())
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


class NoDeadImports(Rule):
    """Detect unused imports in written/edited files."""

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

        # Check if this file should be ignored
        import os
        basename = os.path.basename(file_path)
        if basename in ignore_files:
            return []

        # Extract imported names based on language
        if _is_python_file(file_path):
            names = _extract_python_names(content)
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

        # Find unused names
        unused = []
        for name in names:
            if not name or name.startswith("_"):
                continue
            # Use word boundary to avoid substring false positives
            if not re.search(rf"\b{re.escape(name)}\b", body):
                unused.append(name)

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
