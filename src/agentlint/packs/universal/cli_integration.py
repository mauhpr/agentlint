"""Rule: run external CLI commands on PostToolUse and report violations.

Generic subprocess integration — configure any CLI tool (linter, scanner,
test runner, custom script) as a PostToolUse check. Non-zero exit codes
become violations. All placeholder values are shell-escaped via shlex.quote().
"""
from __future__ import annotations

import logging
import subprocess
from fnmatch import fnmatch

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation
from agentlint.template import build_template_context, resolve_template

logger = logging.getLogger("agentlint")

_MAX_OUTPUT_CHARS = 500
_DEFAULT_TIMEOUT = 10
_DEFAULT_ON = ["Write", "Edit"]
_DEFAULT_GLOB = "**/*"
_DEFAULT_SEVERITY = "warning"

_SEVERITY_MAP = {
    "error": Severity.ERROR,
    "warning": Severity.WARNING,
    "info": Severity.INFO,
}


class CliIntegration(Rule):
    id = "cli-integration"
    description = "Run external CLI tools on file changes and report violations"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        rule_config = context.config.get(self.id, {})
        commands = rule_config.get("commands", [])
        if not commands:
            return []

        template_ctx = build_template_context(context)
        violations: list[Violation] = []

        for cmd_config in commands:
            name = cmd_config.get("name")
            if not name:
                continue

            # Filter by tool name
            on_tools = cmd_config.get("on", _DEFAULT_ON)
            if context.tool_name not in on_tools:
                continue

            # Filter by file glob
            glob_pattern = cmd_config.get("glob", _DEFAULT_GLOB)
            file_path = context.file_path
            if file_path:
                rel = template_ctx.get("file.relative", "")
                if not fnmatch(rel, glob_pattern) and not fnmatch(file_path, glob_pattern):
                    continue
            elif any(k.startswith("file.") for k in _extract_placeholders(cmd_config.get("command", ""))):
                # Command uses file placeholders but no file path available — skip
                continue

            # Resolve command template
            command_template = cmd_config.get("command", "")
            resolved = resolve_template(command_template, template_ctx)
            if resolved is None:
                continue

            # Execute
            timeout = cmd_config.get("timeout", _DEFAULT_TIMEOUT)
            severity_str = cmd_config.get("severity", _DEFAULT_SEVERITY)
            severity = _SEVERITY_MAP.get(severity_str, Severity.WARNING)

            try:
                result = subprocess.run(
                    resolved,
                    shell=True,
                    cwd=context.project_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                logger.warning("CLI command '%s' timed out after %ds", name, timeout)
                continue
            except (FileNotFoundError, OSError) as exc:
                logger.warning("CLI command '%s' failed to start: %s", name, exc)
                continue

            if result.returncode != 0:
                output = (result.stdout or result.stderr or "").strip()
                if len(output) > _MAX_OUTPUT_CHARS:
                    output = output[:_MAX_OUTPUT_CHARS] + "..."
                violations.append(Violation(
                    rule_id=f"{self.id}/{name}",
                    message=output or f"Command exited with code {result.returncode}",
                    severity=severity,
                    file_path=file_path,
                    suggestion=f"Run `{command_template}` to see full output",
                ))

        return violations


def _extract_placeholders(template: str) -> set[str]:
    """Extract placeholder keys from a template string."""
    import re
    return set(re.findall(r"\{([^}]+)\}", template))
