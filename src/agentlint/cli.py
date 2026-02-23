"""AgentLint CLI entry point."""
from __future__ import annotations

import json
import logging
import os
import sys

import click

from agentlint.agents_md import find_agents_md, generate_config, map_to_config, merge_with_existing, parse_agents_md
from agentlint.config import load_config
from agentlint.detector import detect_stack
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext
from agentlint.packs import PACK_MODULES, load_custom_rules, load_rules
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
@click.option("--event", required=True, help="Hook event type (e.g. PreToolUse, PostToolUse, UserPromptSubmit)")
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

    # Build context with event-specific fields
    tool_input = raw.get("tool_input", {})
    context = RuleContext(
        event=hook_event,
        tool_name=raw.get("tool_name", ""),
        tool_input=tool_input,
        project_dir=project_dir,
        config=config.rules,
        session_state=session_state,
        prompt=raw.get("prompt"),
        subagent_output=raw.get("subagent_output"),
        notification_type=raw.get("notification_type"),
        compact_source=raw.get("compact_source"),
    )

    # For PreToolUse Write/Edit, cache current file content for diff-based rules
    if hook_event == HookEvent.PRE_TOOL_USE and context.tool_name in ("Write", "Edit"):
        file_path = context.file_path
        file_content_before = None
        if file_path:
            try:
                with open(file_path, encoding="utf-8", errors="replace") as f:
                    file_content_before = f.read()
            except OSError:
                pass
            if file_content_before is not None:
                file_cache = session_state.setdefault("file_cache", {})
                file_cache[file_path] = file_content_before

        # For Write, the new content is in tool_input
        content = tool_input.get("content", "")
        if content:
            context = RuleContext(
                event=context.event,
                tool_name=context.tool_name,
                tool_input=context.tool_input,
                project_dir=context.project_dir,
                file_content=content,
                file_content_before=file_content_before,
                config=context.config,
                session_state=session_state,
                prompt=context.prompt,
                subagent_output=context.subagent_output,
                notification_type=context.notification_type,
                compact_source=context.compact_source,
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

        # Retrieve cached pre-edit content for diff-based rules
        file_cache = session_state.get("file_cache", {})
        file_content_before = file_cache.pop(file_path, None)

        if file_content is not None:
            context = RuleContext(
                event=context.event,
                tool_name=context.tool_name,
                tool_input=context.tool_input,
                project_dir=context.project_dir,
                file_content=file_content,
                file_content_before=file_content_before,
                config=context.config,
                session_state=session_state,
                prompt=context.prompt,
                subagent_output=context.subagent_output,
                notification_type=context.notification_type,
                compact_source=context.compact_source,
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
  # - security  # opt-in: blocks Bash file writes, network exfiltration

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


@main.command("list-rules")
@click.option("--pack", default=None, help="Filter rules by pack name")
def list_rules(pack: str | None):
    """List all available rules."""
    all_packs = sorted(PACK_MODULES.keys()) if pack is None else [pack]
    rules = load_rules(all_packs)

    if not rules:
        if pack:
            click.echo(f"No rules found for pack '{pack}'.")
        else:
            click.echo("No rules found.")
        return

    # Sort by pack, then by event, then by id.
    rules.sort(key=lambda r: (r.pack, r.events[0].value if r.events else "", r.id))

    # Table header.
    click.echo(f"{'Rule ID':<30} {'Pack':<12} {'Event':<14} {'Severity':<10} Description")
    click.echo("-" * 100)

    for rule in rules:
        event_str = rule.events[0].value if rule.events else "—"
        click.echo(
            f"{rule.id:<30} {rule.pack:<12} {event_str:<14} {rule.severity.value:<10} {rule.description}"
        )

    click.echo(f"\n{len(rules)} rules total.")


@main.command()
@click.option("--project-dir", default=None, help="Project directory")
def status(project_dir: str | None):
    """Show AgentLint status for the current project."""
    from importlib.metadata import version as get_version

    project_dir = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    try:
        ver = get_version("agentlint")
    except Exception:
        ver = "dev"

    config = load_config(project_dir)
    rules = load_rules(config.packs)
    if config.custom_rules_dir:
        rules.extend(load_custom_rules(config.custom_rules_dir, project_dir))

    session_state = load_session()
    budget = session_state.get("token_budget", {})
    total_calls = budget.get("total_calls", 0)

    packs_str = ", ".join(config.packs)
    click.echo(f"AgentLint v{ver} | Severity: {config.severity} | Packs: {packs_str}")
    click.echo(f"Rules: {len(rules)} active | Session: {total_calls} tool calls tracked")


@main.command()
@click.option("--project-dir", default=None, help="Project directory")
def doctor(project_dir: str | None):
    """Diagnose common AgentLint misconfigurations."""
    project_dir = project_dir or os.getcwd()
    issues: list[str] = []
    checks_ok: list[str] = []

    # Check agentlint.yml exists
    config_path = os.path.join(project_dir, "agentlint.yml")
    alt_paths = [
        os.path.join(project_dir, "agentlint.yaml"),
        os.path.join(project_dir, ".agentlint.yml"),
    ]
    if os.path.exists(config_path):
        checks_ok.append("Config file: agentlint.yml found")
    elif any(os.path.exists(p) for p in alt_paths):
        checks_ok.append("Config file: found (alternate name)")
    else:
        issues.append("Config file: agentlint.yml not found. Run 'agentlint init' to create one.")

    # Check hooks registered
    hook_path = settings_path("project", project_dir)
    hook_data = read_settings(hook_path)
    if "hooks" in hook_data and any(
        "agentlint" in str(hook_data["hooks"].get(evt, []))
        for evt in ("PreToolUse", "PostToolUse", "Stop")
    ):
        checks_ok.append("Hooks: installed in .claude/settings.json")
    else:
        issues.append("Hooks: not installed. Run 'agentlint setup' to install.")

    # Check Python version
    import sys as _sys
    py_ver = _sys.version_info
    if py_ver >= (3, 11):
        checks_ok.append(f"Python: {py_ver.major}.{py_ver.minor}.{py_ver.micro} (OK)")
    else:
        issues.append(f"Python: {py_ver.major}.{py_ver.minor} (requires >=3.11)")

    # Check session cache writable
    from agentlint.session import _cache_dir
    cache_dir = _cache_dir()
    if cache_dir.exists() and os.access(str(cache_dir), os.W_OK):
        checks_ok.append(f"Session cache: {cache_dir} (writable)")
    elif not cache_dir.exists():
        checks_ok.append(f"Session cache: {cache_dir} (will be created)")
    else:
        issues.append(f"Session cache: {cache_dir} is not writable")

    for item in checks_ok:
        click.echo(f"  OK  {item}")
    for item in issues:
        click.echo(f"  !!  {item}")

    if issues:
        click.echo(f"\n{len(issues)} issue(s) found.")
    else:
        click.echo("\nAll checks passed.")


@main.command("import-agents-md")
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--dry-run", is_flag=True, help="Preview config without writing")
@click.option("--merge", "merge_mode", is_flag=True, help="Merge with existing agentlint.yml")
def import_agents_md(project_dir: str | None, dry_run: bool, merge_mode: bool):
    """Import conventions from AGENTS.md into AgentLint config."""
    project_dir = project_dir or os.getcwd()

    agents_path = find_agents_md(project_dir)
    if agents_path is None:
        click.echo("No AGENTS.md found in project root.", err=True)
        sys.exit(1)

    sections = parse_agents_md(agents_path)
    if not sections:
        click.echo("AGENTS.md is empty or has no sections.", err=True)
        sys.exit(1)

    mapped = map_to_config(sections)

    click.echo(f"Found AGENTS.md: {agents_path}")
    click.echo(f"Detected packs: {', '.join(mapped.get('packs', []))}")
    rules = mapped.get("rules", {})
    if rules:
        click.echo(f"Detected rules: {', '.join(rules.keys())}")

    config_path = os.path.join(project_dir, "agentlint.yml")

    if merge_mode and os.path.exists(config_path):
        existing_yaml = open(config_path, encoding="utf-8").read()
        output = merge_with_existing(existing_yaml, mapped)
    else:
        output = generate_config(mapped)

    if dry_run:
        click.echo("\n--- Generated config (dry run) ---")
        click.echo(output)
    else:
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(output)
        click.echo(f"Wrote config to {config_path}")


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
