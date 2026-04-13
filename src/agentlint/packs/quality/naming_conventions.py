"""Rule: check file names against configurable naming conventions.

Validates that file names follow expected patterns per language:
- Python: snake_case.py
- JS/TS: camelCase or PascalCase for components
- Test files: test_ prefix or .test. / .spec. suffix
"""
from __future__ import annotations

import re
from pathlib import PurePath

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_CAMEL_CASE_RE = re.compile(r"^[a-z][a-zA-Z0-9]*$")
_PASCAL_CASE_RE = re.compile(r"^[A-Z][a-zA-Z0-9]*$")
_KEBAB_CASE_RE = re.compile(r"^[a-z][a-z0-9-]*$")

_EXT_TO_CONVENTION = {
    "py": "snake_case",
    "rb": "snake_case",
    "rs": "snake_case",
    "go": "snake_case",
    "ts": "camelCase",
    "js": "camelCase",
    "tsx": "PascalCase",
    "jsx": "PascalCase",
}

# TSX/JSX also accept kebab-case (very common in React: my-component.tsx)
_ALTERNATIVE_CONVENTIONS = {
    "tsx": ["kebab-case"],
    "jsx": ["kebab-case"],
}

_CONVENTION_RE = {
    "snake_case": _SNAKE_CASE_RE,
    "camelCase": _CAMEL_CASE_RE,
    "PascalCase": _PASCAL_CASE_RE,
    "kebab-case": _KEBAB_CASE_RE,
}

# Files that are conventionally allowed to break naming rules
_EXEMPT_NAMES = {
    "__init__", "__main__", "conftest", "setup", "index",
    "Makefile", "Dockerfile", "Procfile", "Gemfile", "Rakefile", "Vagrantfile",
}

# Path markers for migration files (Alembic, Django, etc.)
_DEFAULT_MIGRATION_MARKERS = {"migration", "alembic", "versions"}


class NamingConventions(Rule):
    id = "naming-conventions"
    description = "Checks file names against language-specific naming conventions"
    severity = Severity.INFO
    events = [HookEvent.PRE_TOOL_USE]
    pack = "quality"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in ("Write", "Edit"):
            return []

        file_path = context.file_path
        if not file_path:
            return []

        p = PurePath(file_path)
        stem = p.stem
        ext = p.suffix.lstrip(".")

        if not ext or not stem:
            return []

        # Skip exempt files
        if stem in _EXEMPT_NAMES:
            return []

        # Skip test files (they follow their own conventions)
        if stem.startswith("test_") or ".test." in p.name or ".spec." in p.name:
            return []

        # Determine expected convention
        rule_config = context.config.get(self.id, {})

        # Skip migration files (Alembic generates non-standard filenames like 92cd48a3c5f4_msg.py)
        migration_markers = rule_config.get("migration_paths", list(_DEFAULT_MIGRATION_MARKERS))
        if any(marker in file_path.lower() for marker in migration_markers):
            return []

        # User can override per extension: { python: "snake_case", typescript: "camelCase" }
        convention_name = None
        if ext in ("py",) and "python" in rule_config:
            convention_name = rule_config["python"]
        elif ext in ("ts", "js") and "typescript" in rule_config:
            convention_name = rule_config["typescript"]
        elif ext in ("tsx", "jsx") and "react_components" in rule_config:
            convention_name = rule_config["react_components"]
        else:
            convention_name = _EXT_TO_CONVENTION.get(ext)

        if not convention_name:
            return []

        pattern = _CONVENTION_RE.get(convention_name)
        if not pattern:
            return []

        if pattern.match(stem):
            return []

        # Check alternative conventions (e.g., kebab-case for TSX/JSX)
        for alt_name in _ALTERNATIVE_CONVENTIONS.get(ext, []):
            alt_pattern = _CONVENTION_RE.get(alt_name)
            if alt_pattern and alt_pattern.match(stem):
                return []

        return [Violation(
            rule_id=self.id,
            message=f"File '{p.name}' doesn't follow {convention_name} convention",
            severity=self.severity,
            file_path=file_path,
            suggestion=f"Rename to {convention_name} format (e.g., {self._suggest_name(stem, convention_name, ext)})",
        )]

    def _suggest_name(self, stem: str, convention: str, ext: str) -> str:
        """Generate a suggested filename in the target convention."""
        # Split on common separators
        words = re.split(r"[-_\s]+|(?<=[a-z])(?=[A-Z])", stem)
        words = [w.lower() for w in words if w]

        if convention == "snake_case":
            return "_".join(words) + f".{ext}"
        elif convention == "camelCase":
            return words[0] + "".join(w.capitalize() for w in words[1:]) + f".{ext}"
        elif convention == "PascalCase":
            return "".join(w.capitalize() for w in words) + f".{ext}"
        return f"{stem}.{ext}"
