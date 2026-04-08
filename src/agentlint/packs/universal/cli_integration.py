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


def _filter_diff_violations(
    output: str, content_before: str | None, content_after: str | None,
) -> str:
    """Filter CLI output to only violations on changed lines."""
    if content_before is None or content_after is None:
        return output  # new file or no before content — show everything

    import difflib
    before_lines = content_before.splitlines(keepends=True)
    after_lines = content_after.splitlines(keepends=True)
    changed_lines: set[int] = set()

    for group in difflib.SequenceMatcher(None, before_lines, after_lines).get_opcodes():
        tag, _, _, j1, j2 = group
        if tag in ("replace", "insert"):
            changed_lines.update(range(j1 + 1, j2 + 1))  # 1-indexed

    if not changed_lines:
        return ""  # no changes — suppress all output

    import re
    filtered = []
    for line in output.splitlines():
        match = re.search(r":(\d+)(?:[:\s]|$)|line\s+(\d+)", line)
        if match:
            lineno = int(match.group(1) or match.group(2))
            if lineno in changed_lines:
                filtered.append(line)
        else:
            # Non-line-specific output (headers, summaries) — keep
            filtered.append(line)

    return "\n".join(filtered)


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

        # Global defaults from rule config (top-level keys)
        global_timeout = rule_config.get("timeout", _DEFAULT_TIMEOUT)
        global_severity = rule_config.get("severity", _DEFAULT_SEVERITY)
        global_diff_only = rule_config.get("diff_only", False)
        global_max_output = rule_config.get("max_output", _MAX_OUTPUT_CHARS)
        global_on = rule_config.get("on", _DEFAULT_ON)

        template_ctx = build_template_context(context)
        violations: list[Violation] = []

        for cmd_config in commands:
            name = cmd_config.get("name")
            if not name:
                continue

            # Filter by tool name (per-command overrides global)
            on_tools = cmd_config.get("on", global_on)
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

            # Per-command overrides global defaults
            timeout = cmd_config.get("timeout", global_timeout)
            severity_str = cmd_config.get("severity", global_severity)
            severity = _SEVERITY_MAP.get(severity_str, Severity.WARNING)
            diff_only = cmd_config.get("diff_only", global_diff_only)
            max_output = cmd_config.get("max_output", global_max_output)
            mode = cmd_config.get("mode", "check")

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

            # auto-fix mode: run silently, only warn on actual failure
            if mode == "auto-fix":
                if result.returncode != 0:
                    output = (result.stdout or result.stderr or "").strip()
                    if output and len(output) > max_output:
                        output = output[:max_output] + "..."
                    violations.append(Violation(
                        rule_id=f"{self.id}/{name}",
                        message=output or f"Auto-fix failed with code {result.returncode}",
                        severity=severity,
                        file_path=file_path,
                        suggestion=f"Run `{command_template}` manually to debug",
                    ))
                else:
                    logger.debug("Auto-fix '%s' succeeded on %s", name, file_path or "(no file)")
                continue

            if result.returncode != 0:
                output = (result.stdout or result.stderr or "").strip()

                # diff_only: filter to changed lines only
                if diff_only:
                    output = _filter_diff_violations(
                        output, context.file_content_before, context.file_content,
                    )
                    if not output:
                        continue  # all violations were pre-existing

                if len(output) > max_output:
                    output = output[:max_output] + "..."
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
