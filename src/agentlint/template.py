"""Template engine for CLI integration command placeholders.

Resolves {placeholder} strings in command templates using values from
RuleContext. All values are shell-escaped via shlex.quote() to prevent
injection attacks from adversarial file names or environment variables.
"""
from __future__ import annotations

import logging
import os
import re
import shlex
from pathlib import Path

from agentlint.models import RuleContext

logger = logging.getLogger("agentlint")


def is_path_within_project(file_path: str, project_dir: str) -> bool:
    """Check if file_path is within project_dir (realpath-based)."""
    resolved = os.path.realpath(file_path)
    project_real = os.path.realpath(project_dir)
    return resolved.startswith(project_real + os.sep) or resolved == project_real


def build_template_context(context: RuleContext) -> dict[str, str]:
    """Build the flat placeholder namespace from a RuleContext."""
    ctx: dict[str, str] = {}

    ctx["project.dir"] = context.project_dir
    ctx["tool.name"] = context.tool_name

    # File-derived placeholders (only if file is within project)
    file_path = context.file_path
    if file_path and is_path_within_project(file_path, context.project_dir):
        p = Path(file_path)
        ctx["file.path"] = str(p)
        ctx["file.name"] = p.name
        ctx["file.stem"] = p.stem
        ctx["file.ext"] = p.suffix.lstrip(".")
        ctx["file.dir"] = str(p.parent)
        try:
            ctx["file.relative"] = str(p.relative_to(context.project_dir))
            ctx["file.dir.relative"] = str(p.parent.relative_to(context.project_dir))
        except ValueError:
            pass

    # Session state
    touched = context.session_state.get("files_touched", [])
    ctx["session.changed_files"] = " ".join(touched)

    return ctx


def resolve_template(template: str, ctx: dict[str, str]) -> str | None:
    """Resolve {placeholders} in a command template.

    All values are shell-escaped via shlex.quote(). Returns None if any
    non-env placeholder is missing (command should be skipped).
    """
    missing: list[str] = []

    def _replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        # {env.*} reads from environment — empty string if missing, never skips
        if key.startswith("env."):
            return shlex.quote(os.environ.get(key[4:], ""))
        val = ctx.get(key)
        if val is None:
            missing.append(key)
            return ""
        return shlex.quote(val)

    result = re.sub(r"\{([^}]+)\}", _replacer, template)

    if missing:
        logger.debug("Skipping command — unresolvable placeholders: %s", missing)
        return None
    return result
