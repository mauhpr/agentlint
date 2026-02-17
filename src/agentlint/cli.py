"""AgentLint CLI entry point."""
from __future__ import annotations

import json
import os
import sys

import click

from agentlint.config import load_config
from agentlint.detector import detect_stack
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext
from agentlint.packs import load_rules
from agentlint.reporter import Reporter


@click.group()
def main():
    """AgentLint - Real-time quality guardrails for AI coding agents."""


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
    except json.JSONDecodeError:
        raw = {}

    config = load_config(project_dir)
    rules = load_rules(config.packs)

    # Build context
    tool_input = raw.get("tool_input", {})
    context = RuleContext(
        event=hook_event,
        tool_name=raw.get("tool_name", ""),
        tool_input=tool_input,
        project_dir=project_dir,
        config=config.rules,
    )

    # For PostToolUse on file operations, try to read file content
    if hook_event == HookEvent.POST_TOOL_USE and context.file_path:
        try:
            with open(context.file_path) as f:
                context = RuleContext(
                    event=context.event,
                    tool_name=context.tool_name,
                    tool_input=context.tool_input,
                    project_dir=context.project_dir,
                    file_content=f.read(),
                    config=context.config,
                    session_state=context.session_state,
                )
        except (FileNotFoundError, PermissionError):
            pass

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
                session_state=context.session_state,
            )

    engine = Engine(config=config, rules=rules)
    result = engine.evaluate(context)

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
# Docs: https://github.com/maupr92/agentlint

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
    except json.JSONDecodeError:
        pass

    reporter = Reporter(violations=[], rules_evaluated=0)
    report_text = reporter.format_session_report(files_changed=0)
    output = json.dumps({"systemMessage": report_text, "continue": True})
    click.echo(output)


if __name__ == "__main__":
    main()
