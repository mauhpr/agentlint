"""Rule: warn on import/require of a package with active GHSA advisories.

Hybrid rule (Phase 19) — sibling to no-vulnerable-version-install.
Where that one matches *pinned installs* (and knows the version), this
one matches *imports / requires* in source code (which usually have no
inline version).

The trade-off:
    The import statement doesn't know the version, so we can't make
    the same precise "this version is vulnerable" claim. We can only
    say "this package CURRENTLY has open advisories — verify your
    locked version is past the fix." That's WARNING severity, not ERROR.

Self-degrading: when AgentChute is not configured, the rule is a no-op.
The OSS user gets nothing extra; only AgentChute-licensed teams get
the import-time GHSA cross-reference.

Sourcing: same ``ghsa-vulns`` cloud feed as no-vulnerable-version-install.
The OSS rule reads the feed once, builds a set of (ecosystem, package)
tuples, and does O(1) lookups against parsed imports.

Limitations (V0):
    - Only covers JS/TS (``import`` and ``require``) and Python
      (``import``, ``from``). Java/Go/Rust import-statement parsing
      is post-V0.
    - Doesn't try to resolve relative imports — ``import ./local`` is
      ignored.
    - Doesn't dedupe across an Edit + Write of the same file in the
      same session — the developer might see the warning twice. The
      Phase 14 dashboard's session-level dedup makes this harmless.
"""

from __future__ import annotations

import re
from typing import Any

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation


_FILE_TOOLS = {"Edit", "Write"}


# JS/TS — handles `import x from 'pkg'`, `import 'pkg'`, `require('pkg')`,
# `import('pkg')` (dynamic), `from 'pkg'`. Captures the package spec
# inside the quotes; the helper below trims subpaths/scopes.
_JS_IMPORT_PATTERNS = [
    re.compile(r"""(?:^|\W)import\s+(?:[^"';]*?\s+from\s+)?["']([^"']+)["']""", re.MULTILINE),
    re.compile(r"""(?:^|\W)require\s*\(\s*["']([^"']+)["']\s*\)"""),
    re.compile(r"""(?:^|\W)import\s*\(\s*["']([^"']+)["']\s*\)"""),
]

# Python — `import foo`, `import foo.bar`, `from foo import x`,
# `from foo.bar import y`. Captures the top-level package.
_PY_IMPORT_PATTERNS = [
    re.compile(r"^\s*import\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.MULTILINE),
    re.compile(r"^\s*from\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.MULTILINE),
]


# Python stdlib short-list (so we don't query GHSA for `os` or `json`).
# Partial allowlist — anything not on it falls through to the feed
# lookup, which itself returns nothing for non-PyPI packages.
_PYTHON_STDLIB = frozenset({
    "os", "sys", "re", "json", "math", "time", "datetime", "logging",
    "pathlib", "subprocess", "shutil", "tempfile", "threading", "asyncio",
    "typing", "functools", "itertools", "collections", "enum", "dataclasses",
    "abc", "io", "uuid", "hashlib", "hmac", "secrets", "base64", "urllib",
    "http", "ssl", "socket", "selectors", "platform", "warnings",
    "csv", "configparser", "argparse", "unittest", "ast", "inspect", "copy",
    "contextlib", "weakref", "gc", "operator", "string", "textwrap",
    "tomllib", "zipfile", "tarfile", "glob", "fnmatch", "errno", "signal",
    "atexit", "traceback", "decimal", "fractions", "statistics", "random",
})


def _strip_js_pkg(spec: str) -> str | None:
    """Normalize a JS import spec to a bare package name.

    - ``react`` → ``react``
    - ``react/jsx-runtime`` → ``react``
    - ``@types/node`` → ``@types/node``
    - ``@scope/pkg/sub`` → ``@scope/pkg``
    - ``./local`` → None (relative, not on registry)
    - ``../foo`` → None
    - ``/abs/path`` → None
    - ``node:fs`` → None (Node built-in)
    """
    if not spec:
        return None
    if spec.startswith(("./", "../", "/")):
        return None
    if spec.startswith("node:"):
        return None
    if spec.startswith("@"):
        parts = spec.split("/", 2)
        if len(parts) < 2:
            return None
        return f"{parts[0]}/{parts[1]}".lower()
    return spec.split("/", 1)[0].lower()


def _extract_imports(content: str, file_path: str | None) -> list[tuple[str, str]]:
    """Return ``[(ecosystem_osv, package_name), ...]`` extracted from
    ``content`` based on the file extension."""
    if not content:
        return []

    out: list[tuple[str, str]] = []
    ext = (file_path or "").lower().rsplit(".", 1)[-1] if file_path else ""

    is_js = ext in {"js", "jsx", "mjs", "cjs", "ts", "tsx"}
    is_py = ext == "py"

    # If extension is unknown but content looks JS/TS-ish, still try JS.
    # Likewise for Python. Bias toward JS — most common case.
    if not (is_js or is_py):
        if any(kw in content for kw in (" from '", ' from "', "require(", "import(")):
            is_js = True
        elif "from " in content and "import " in content:
            is_py = True

    if is_js:
        for pattern in _JS_IMPORT_PATTERNS:
            for match in pattern.finditer(content):
                pkg = _strip_js_pkg(match.group(1))
                if pkg:
                    out.append(("npm", pkg))

    if is_py:
        for pattern in _PY_IMPORT_PATTERNS:
            for match in pattern.finditer(content):
                pkg = match.group(1).lower()
                if pkg in _PYTHON_STDLIB:
                    continue
                out.append(("PyPI", pkg))

    # Dedupe within the file
    return sorted(set(out))


class NoVulnerableImport(Rule):
    """WARNING-level rule that flags imports of packages currently
    listed in the GHSA feed. Use as an attention-getter — the rule
    cannot know which version the user is locked at."""

    id = "no-vulnerable-import"
    description = (
        "Warns when source code imports a package that has open GHSA "
        "advisories. Verify your locked version is past the fix."
    )
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _FILE_TOOLS:
            return []

        # Edit tools deliver new content under different keys depending
        # on the agent's call form. Match the env_credential_reference pattern.
        content = (
            context.tool_input.get("new_string")
            or context.tool_input.get("content")
            or ""
        )
        if not content:
            return []

        file_path = context.tool_input.get("file_path") or context.file_path
        imports = _extract_imports(content, file_path)
        if not imports:
            return []

        # Lazy import: keep cold-start fast for OSS users not on AgentChute.
        try:
            from agentlint.agentchute import cloud_feed
        except ImportError:
            return []

        feed_data = cloud_feed.get("ghsa-vulns", default={"records": []}, allow_network=False)
        if not isinstance(feed_data, dict):
            return []
        records = feed_data.get("records") or []
        if not records:
            return []

        # Build (ecosystem, package) → list of GHSA records
        index: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for rec in records:
            if not isinstance(rec, dict):
                continue
            eco = rec.get("ecosystem")
            pkg = rec.get("package")
            if not eco or not pkg:
                continue
            index.setdefault((eco, pkg.lower()), []).append(rec)

        violations: list[Violation] = []
        for ecosystem, name in imports:
            matches = index.get((ecosystem, name)) or []
            if not matches:
                continue
            # At most ONE warning per (file, package); pick the most-severe.
            rank = {
                "CRITICAL": 4, "HIGH": 3, "MODERATE": 2,
                "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0, None: 0,
            }
            best = max(matches, key=lambda r: rank.get(r.get("severity"), 0))
            ghsa = best.get("ghsa_id", "GHSA-?")
            sev = best.get("severity") or "UNKNOWN"
            summary = (best.get("summary") or "").strip()
            suffix = f" — {summary}" if summary else ""
            violations.append(
                Violation(
                    rule_id=self.id,
                    message=(
                        f"Import of {ecosystem}:{name} — open advisory {ghsa} "
                        f"(severity: {sev}){suffix}"
                    ),
                    severity=self.severity,
                    file_path=file_path,
                    suggestion=(
                        f"Confirm your locked version of {name} is past the "
                        f"affected range listed in {ghsa}. Use "
                        f"`npm audit` / `pip-audit` to verify."
                    ),
                )
            )

        return violations
