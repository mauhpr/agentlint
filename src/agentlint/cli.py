"""AgentLint CLI entry point."""
from __future__ import annotations

import json
import logging
import os
import sys

import click

from agentlint.config import load_config
from agentlint.detector import detect_stack
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext
from agentlint.packs import load_custom_rules, load_rules
from agentlint.reporter import Reporter
from agentlint.session import cleanup_session, load_session, save_session
from agentlint.setup import _resolve_command, merge_hooks, read_settings, remove_hooks, settings_path, write_settings
from agentlint.utils.git import get_changed_files

logger = logging.getLogger("agentlint")


def _configure_logging() -> None:
    level = os.environ.get("AGENTLINT_LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.WARNING),
        format="%(name)s: %(message)s",
        stream=sys.stderr,
    )


@click.group()
def main():
    """AgentLint - Real-time quality guardrails for AI coding agents."""
    _configure_logging()


@main.command()
@click.option("--event", required=True, help="Hook event type (PreToolUse, PostToolUse, Stop)")
@click.option("--project-dir", default=None, help="Project directory")
def check(event: str, project_dir: str | None):
    """Evaluate rules against a tool call from stdin."""
    project_dir = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    hook_event = HookEvent.from_string(event)

    # Read tool input from stdin
    try:
        raw = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        raw = {}

    config = load_config(project_dir)
    rules = load_rules(config.packs)
    if config.custom_rules_dir:
        rules.extend(load_custom_rules(config.custom_rules_dir, project_dir))

    # Load persisted session state
    session_state = load_session()

    # Build context
    tool_input = raw.get("tool_input", {})
    context = RuleContext(
        event=hook_event,
        tool_name=raw.get("tool_name", ""),
        tool_input=tool_input,
        project_dir=project_dir,
        config=config.rules,
        session_state=session_state,
    )

    # For PostToolUse on file operations, try to read file content
    if hook_event == HookEvent.POST_TOOL_USE and context.file_path:
        file_path = context.file_path
        # Validate path is relative to project dir
        try:
            resolved = os.path.realpath(file_path)
            project_real = os.path.realpath(project_dir)
            if not resolved.startswith(project_real + os.sep) and resolved != project_real:
                logger.warning("Path traversal blocked: %s", file_path)
                file_content = None
            else:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    file_content = f.read()
        except OSError:
            file_content = None

        if file_content is not None:
            context = RuleContext(
                event=context.event,
                tool_name=context.tool_name,
                tool_input=context.tool_input,
                project_dir=context.project_dir,
                file_content=file_content,
                config=context.config,
                session_state=session_state,
            )

    # For PreToolUse Write, content is in tool_input
    if hook_event == HookEvent.PRE_TOOL_USE and context.tool_name == "Write":
        content = tool_input.get("content", "")
        if content:
            context = RuleContext(
                event=context.event,
                tool_name=context.tool_name,
                tool_input=context.tool_input,
                project_dir=context.project_dir,
                file_content=content,
                config=context.config,
                session_state=session_state,
            )

    engine = Engine(config=config, rules=rules)
    result = engine.evaluate(context)

    # Persist session state after evaluation (rules may have mutated it)
    save_session(session_state)

    reporter = Reporter(violations=result.violations, rules_evaluated=result.rules_evaluated)
    output = reporter.format_hook_output()
    if output:
        click.echo(output)

    sys.exit(reporter.exit_code())


@main.command()
@click.option("--project-dir", default=None, help="Project directory")
def init(project_dir: str | None):
    """Initialize AgentLint config in the project."""
    project_dir = project_dir or os.getcwd()
    packs = detect_stack(project_dir)

    pack_lines = "\n".join(f"  - {p}" for p in packs)
    config_content = f"""# AgentLint Configuration
# Docs: https://github.com/mauhpr/agentlint

stack: auto

severity: standard  # strict | standard | relaxed

packs:
{pack_lines}

rules: {{}}
  # Override individual rules:
  # no-secrets:
  #   severity: error
  # max-file-size:
  #   limit: 300

# custom_rules_dir: .agentlint/rules/
"""
    config_path = os.path.join(project_dir, "agentlint.yml")
    with open(config_path, "w") as f:
        f.write(config_content)

    click.echo(f"Created {config_path}")
    click.echo(f"Detected packs: {', '.join(packs)}")


@main.command()
@click.option("--project-dir", default=None, help="Project directory")
def report(project_dir: str | None):
    """Generate session summary report (for Stop event)."""
    project_dir = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        pass

    # Load session and populate changed_files via git
    session_state = load_session()
    changed_files = session_state.get("changed_files") or get_changed_files(project_dir)
    session_state["changed_files"] = changed_files

    # Evaluate Stop rules to collect end-of-session violations
    config = load_config(project_dir)
    rules = load_rules(config.packs)
    if config.custom_rules_dir:
        rules.extend(load_custom_rules(config.custom_rules_dir, project_dir))

    context = RuleContext(
        event=HookEvent.STOP,
        tool_name="",
        tool_input={},
        project_dir=project_dir,
        config=config.rules,
        session_state=session_state,
    )

    engine = Engine(config=config, rules=rules)
    result = engine.evaluate(context)

    reporter = Reporter(violations=result.violations, rules_evaluated=result.rules_evaluated)
    report_text = reporter.format_session_report(files_changed=len(changed_files))
    output = json.dumps({"systemMessage": report_text, "continue": True})
    click.echo(output)

    # Clean up session file
    cleanup_session()


@main.command()
@click.option("--global", "scope", flag_value="user", help="Install to ~/.claude/settings.json")
@click.option(
    "--project", "scope", flag_value="project", default=True, help="Install to .claude/settings.json (default)"
)
@click.option("--project-dir", default=None, help="Project directory")
def setup(scope: str, project_dir: str | None):
    """Install AgentLint hooks into Claude Code settings."""
    project_dir = project_dir or os.getcwd()

    agentlint_cmd = _resolve_command()
    click.echo(f"Resolved agentlint: {agentlint_cmd}")

    path = settings_path(scope, project_dir)
    existing = read_settings(path)
    updated = merge_hooks(existing, agentlint_cmd=agentlint_cmd)
    write_settings(path, updated)

    click.echo(f"Installed AgentLint hooks in {path}")

    # Also create agentlint.yml if it doesn't exist
    config_path = os.path.join(project_dir, "agentlint.yml")
    if not os.path.exists(config_path):
        ctx = click.Context(init)
        ctx.invoke(init, project_dir=project_dir)


@main.command()
@click.option("--global", "scope", flag_value="user", help="Remove from ~/.claude/settings.json")
@click.option(
    "--project", "scope", flag_value="project", default=True, help="Remove from .claude/settings.json (default)"
)
@click.option("--project-dir", default=None, help="Project directory")
def uninstall(scope: str, project_dir: str | None):
    """Remove AgentLint hooks from Claude Code settings."""
    project_dir = project_dir or os.getcwd()

    path = settings_path(scope, project_dir)
    existing = read_settings(path)
    updated = remove_hooks(existing)

    if updated:
        write_settings(path, updated)
    elif path.exists():
        path.unlink()

    click.echo(f"Removed AgentLint hooks from {path}")


if __name__ == "__main__":
    main()
