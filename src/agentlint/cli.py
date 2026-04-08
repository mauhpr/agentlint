"""AgentLint CLI entry point."""
from __future__ import annotations

import json
import logging
import os
import sys
import time

import click

from agentlint.agents_md import find_agents_md, generate_config, map_to_config, merge_with_existing, parse_agents_md
from agentlint.config import load_config
from agentlint.detector import detect_stack
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs import PACK_MODULES, load_custom_rules, load_rules
from agentlint.reporter import Reporter
from agentlint.session import cleanup_session, load_session, save_session
from agentlint.setup import _resolve_command, merge_hooks, read_settings, remove_hooks, settings_path, write_settings
from agentlint.utils.git import get_changed_files, get_diff_files

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

    # Merge circuit breaker settings into rules config under a reserved key
    rules_config = config.rules
    if config.circuit_breaker:
        rules_config = {**rules_config, "_circuit_breaker_global": config.circuit_breaker}

    # Load persisted session state
    session_state = load_session()

    # Build context with event-specific fields
    tool_input = raw.get("tool_input", {})
    context = RuleContext(
        event=hook_event,
        tool_name=raw.get("tool_name", ""),
        tool_input=tool_input,
        project_dir=project_dir,
        config=rules_config,
        session_state=session_state,
        prompt=raw.get("prompt"),
        # Claude Code sends "last_assistant_message" for SubagentStop;
        # "subagent_output" is a legacy field name kept for backward compatibility.
        subagent_output=raw.get("last_assistant_message") or raw.get("subagent_output"),
        notification_type=raw.get("notification_type"),
        compact_source=raw.get("compact_source"),
        agent_transcript_path=raw.get("agent_transcript_path"),
        agent_type=raw.get("agent_type"),
        agent_id=raw.get("agent_id"),
    )

    # Track files touched during the session for the Stop report
    if context.file_path:
        touched = session_state.setdefault("files_touched", [])
        if context.file_path not in touched:
            touched.append(context.file_path)

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
                agent_transcript_path=context.agent_transcript_path,
                agent_type=context.agent_type,
                agent_id=context.agent_id,
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
                agent_transcript_path=context.agent_transcript_path,
                agent_type=context.agent_type,
                agent_id=context.agent_id,
            )

    # Resolve project-specific packs for monorepo
    effective_config = config
    if context.file_path and config.projects:
        effective_packs = config.resolve_packs_for_file(context.file_path, project_dir)
        effective_config = config.with_packs(effective_packs)

    engine = Engine(config=effective_config, rules=rules)
    result = engine.evaluate(context)

    # Record event for product insights (opt-in)
    try:
        from agentlint.recorder import is_recording_enabled
        if is_recording_enabled(config):
            from agentlint.recorder import append_event, summarize_tool_input
            from agentlint.session import _session_key
            append_event({
                "v": 1,
                "ts": time.time(),
                "event": event,
                "tool_name": raw.get("tool_name", ""),
                "tool_summary": summarize_tool_input(
                    raw.get("tool_name", ""), tool_input, raw.get("prompt"),
                ),
                "violations": [
                    {"rule_id": v.rule_id, "severity": v.severity.value}
                    for v in result.violations
                ],
                "rules_evaluated": result.rules_evaluated,
                "is_blocking": result.is_blocking,
                "project_dir": project_dir,
                "agent_type": raw.get("agent_type"),
            }, key=_session_key())
    except Exception:
        logger.warning("Failed to write recording event", exc_info=True)

    # Persist session state after evaluation (rules may have mutated it)
    save_session(session_state)

    reporter = Reporter(violations=result.violations, rules_evaluated=result.rules_evaluated)
    if event == "SubagentStart":
        output = reporter.format_subagent_start_output()
    else:
        output = reporter.format_hook_output(event=event)
    if output:
        click.echo(output)

    sys.exit(reporter.exit_code(event=event))


@main.command()
@click.option("--diff", default=None, help="Git diff range (e.g., origin/main...HEAD)")
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]))
def ci(diff: str | None, project_dir: str | None, output_format: str):
    """Scan changed files and report violations for CI pipelines."""
    project_dir = project_dir or os.getcwd()

    config = load_config(project_dir)
    rules = load_rules(config.packs)
    if config.custom_rules_dir:
        rules.extend(load_custom_rules(config.custom_rules_dir, project_dir))

    changed_files = get_diff_files(project_dir, diff)
    if not changed_files:
        if output_format == "json":
            click.echo(json.dumps({"violations": [], "files_scanned": 0, "rules_evaluated": 0}))
        else:
            click.echo("No changed files found.")
        sys.exit(0)

    all_violations: list = []
    total_evaluated = 0

    for file_path in changed_files:
        try:
            with open(file_path, "rb") as fb:
                head = fb.read(512)
            if b"\x00" in head:
                continue  # skip binary files
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError:
            continue

        # Resolve project-specific packs for monorepo
        effective_config = config
        if config.projects:
            effective_packs = config.resolve_packs_for_file(file_path, project_dir)
            effective_config = config.with_packs(effective_packs)
        engine = Engine(config=effective_config, rules=rules)

        # Run PreToolUse (catches secrets, env, file-scope) and PostToolUse (file quality)
        for event in (HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE):
            context = RuleContext(
                event=event,
                tool_name="Write",
                tool_input={"file_path": file_path, "content": content},
                project_dir=project_dir,
                file_content=content,
                config=effective_config.rules,
            )
            result = engine.evaluate(context)
            all_violations.extend(result.violations)
            total_evaluated += result.rules_evaluated

    has_errors = any(v.severity == Severity.ERROR for v in all_violations)
    errors = [v for v in all_violations if v.severity == Severity.ERROR]
    warnings = [v for v in all_violations if v.severity == Severity.WARNING]
    infos = [v for v in all_violations if v.severity == Severity.INFO]

    if output_format == "json":
        click.echo(json.dumps({
            "violations": [v.to_dict() for v in all_violations],
            "files_scanned": len(changed_files),
            "rules_evaluated": total_evaluated,
        }))
    else:
        if not all_violations:
            click.echo(f"Clean — {len(changed_files)} files scanned, {total_evaluated} rules evaluated.")
        else:
            for v in all_violations:
                sev = v.severity.value.upper()
                loc = f"{v.file_path}" if v.file_path else "?"
                click.echo(f"{loc}  [{v.rule_id}] {sev}  {v.message}")
                if v.suggestion:
                    click.echo(f"  → {v.suggestion}")
                click.echo()
            click.echo(
                f"{len(all_violations)} violation(s) "
                f"({len(errors)} error, {len(warnings)} warning, {len(infos)} info) "
                f"in {len(changed_files)} files"
            )

    sys.exit(1 if has_errors else 0)


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
  # - autopilot  # opt-in: production guard, cloud/infra safety, CI/CD pipeline, docker, firewall
  # - mypack     # custom packs: add name here + set custom_rules_dir below

rules: {{}}
  # Override individual rules:
  # no-secrets:
  #   severity: error
  # max-file-size:
  #   limit: 300

# recording:
#   enabled: false  # opt-in session recording for product insights

# custom_rules_dir: .agentlint/rules/
# Custom rules with pack = "mypack" activate when "mypack" is listed in packs above
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

    # Load session and populate changed_files
    # Combine: files tracked during the session + git diff (for any we missed)
    session_state = load_session()
    git_files = set(get_changed_files(project_dir))
    session_files = set(session_state.get("files_touched", []))
    changed_files = sorted(git_files | session_files)
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
    cb_state = session_state.get("circuit_breaker", {})
    report_text = reporter.format_session_report(
        files_changed=len(changed_files),
        cb_state=cb_state,
        session_state=session_state,
    )
    output = json.dumps({"systemMessage": report_text, "continue": True})
    click.echo(output)

    # Record final summary entry
    try:
        from agentlint.recorder import is_recording_enabled
        if is_recording_enabled(config):
            from agentlint.recorder import append_event
            from agentlint.session import _session_key
            append_event({
                "v": 1,
                "ts": time.time(),
                "event": "Stop",
                "tool_name": "",
                "violations": [
                    {"rule_id": v.rule_id, "severity": v.severity.value}
                    for v in result.violations
                ],
                "rules_evaluated": result.rules_evaluated,
                "is_blocking": result.is_blocking,
                "project_dir": project_dir,
                "files_changed": len(changed_files),
            }, key=_session_key())
    except Exception:
        logger.warning("Failed to write recording event", exc_info=True)

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
@click.option("--project-dir", default=None, help="Project directory")
def list_rules(pack: str | None, project_dir: str | None):
    """List all available rules."""
    project_dir = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    builtin_packs = sorted(PACK_MODULES.keys()) if pack is None else [p for p in [pack] if p in PACK_MODULES]
    rules = load_rules(builtin_packs)

    # Load custom rules
    config = load_config(project_dir)
    if config.custom_rules_dir:
        custom = load_custom_rules(config.custom_rules_dir, project_dir)
        if pack is not None:
            custom = [r for r in custom if r.pack == pack]
        rules.extend(custom)

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
        custom = load_custom_rules(config.custom_rules_dir, project_dir)
        rules.extend(r for r in custom if r.pack in config.packs)

    session_state = load_session()
    budget = session_state.get("token_budget", {})
    total_calls = budget.get("total_calls", 0)

    packs_str = ", ".join(config.packs)
    click.echo(f"AgentLint v{ver} | Severity: {config.severity} | Packs: {packs_str}")
    click.echo(f"Rules: {len(rules)} active | Session: {total_calls} tool calls tracked")

    if config.projects:
        click.echo("Projects:")
        for prefix, proj in sorted(config.projects.items()):
            proj_packs = ", ".join(proj.get("packs", []))
            click.echo(f"  {prefix} → {proj_packs}")


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

    # Check custom rules
    config = load_config(project_dir)
    if config.custom_rules_dir:
        from pathlib import Path as _Path
        custom_dir = _Path(project_dir) / config.custom_rules_dir
        if custom_dir.is_dir():
            py_files = [f for f in custom_dir.glob("*.py") if not f.name.startswith("_")]
            if py_files:
                checks_ok.append(f"Custom rules: {len(py_files)} rule file(s) in {config.custom_rules_dir}")
                # Check for orphaned packs (rules whose pack isn't in packs: list)
                custom_rules = load_custom_rules(config.custom_rules_dir, project_dir)
                orphaned = {r.pack for r in custom_rules} - set(config.packs)
                for p in sorted(orphaned):
                    issues.append(f"Custom pack '{p}' not in packs: list — rules will be skipped")
            else:
                issues.append(f"Custom rules: {config.custom_rules_dir} exists but has no .py files")
        else:
            issues.append(f"Custom rules: {config.custom_rules_dir} configured but directory not found")

    # Check CLI integration commands
    import shutil
    cli_config = config.rules.get("cli-integration", {})
    cli_commands = cli_config.get("commands", [])
    if cli_commands:
        for cmd_cfg in cli_commands:
            name = cmd_cfg.get("name", "unnamed")
            command = cmd_cfg.get("command", "")
            # Extract the binary name (first word, ignoring placeholders)
            binary = command.split()[0] if command else ""
            if binary and not binary.startswith("{"):
                if shutil.which(binary):
                    checks_ok.append(f"CLI integration: '{name}' → {binary} found")
                else:
                    issues.append(f"CLI integration: '{name}' → {binary} not found in PATH")

    # Suggest CLI integration recipes for detected tools
    if not cli_commands:
        _TOOL_RECIPES = ["ruff", "mypy", "pytest", "black"]
        for tool in _TOOL_RECIPES:
            if shutil.which(tool):
                checks_ok.append(f"CLI recipe: {tool} found — consider adding to cli-integration")

    # Check recordings dir writable (when recording is enabled)
    from agentlint.recorder import is_recording_enabled
    if is_recording_enabled(config):
        from agentlint.recorder import _recordings_dir
        rec_dir = _recordings_dir()
        if rec_dir.exists() and os.access(str(rec_dir), os.W_OK):
            checks_ok.append(f"Recordings dir: {rec_dir} (writable)")
        elif not rec_dir.exists():
            checks_ok.append(f"Recordings dir: {rec_dir} (will be created)")
        else:
            issues.append(f"Recordings dir: {rec_dir} is not writable")

    for item in checks_ok:
        click.echo(f"  OK  {item}")
    for item in issues:
        click.echo(f"  !!  {item}")

    if issues:
        click.echo(f"\n{len(issues)} issue(s) found.")
    else:
        click.echo("\nAll checks passed.")


@main.command()
@click.argument("rule_id", required=False)
@click.option("--list", "list_mode", is_flag=True, help="Show suppressed rules")
@click.option("--clear", is_flag=True, help="Clear all suppressions")
def suppress(rule_id: str | None, list_mode: bool, clear: bool):
    """Suppress a warning rule for the rest of the session."""
    session_state = load_session()
    suppressed = session_state.setdefault("suppressed_rules", [])

    if clear:
        session_state["suppressed_rules"] = []
        save_session(session_state)
        click.echo("All suppressions cleared.")
    elif list_mode:
        if suppressed:
            for rid in suppressed:
                click.echo(f"  {rid}")
        else:
            click.echo("No rules suppressed.")
    elif rule_id:
        if rule_id not in suppressed:
            suppressed.append(rule_id)
        save_session(session_state)
        click.echo(f"Suppressed '{rule_id}' for this session.")
    else:
        click.echo("Usage: agentlint suppress RULE_ID | --list | --clear")


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


@main.group()
def recordings():
    """Manage session recordings."""


@recordings.command("list")
def recordings_list():
    """Show all recordings (session key, date, event count)."""
    from datetime import datetime

    from agentlint.recorder import list_recordings as _list_recordings

    recs = _list_recordings()
    if not recs:
        click.echo("No recordings found.")
        return

    click.echo(f"{'Session Key':<40} {'Date':<20} {'Events':>7} {'Size':>10}")
    click.echo("-" * 80)
    for r in recs:
        dt = datetime.fromtimestamp(r["modified"]).strftime("%Y-%m-%d %H:%M")
        size_kb = r["size_bytes"] / 1024
        click.echo(f"{r['session_key']:<40} {dt:<20} {r['event_count']:>7} {size_kb:>8.1f} KB")

    click.echo(f"\n{len(recs)} recording(s).")


@recordings.command("show")
@click.argument("key")
@click.option("--violations-only", is_flag=True, help="Only show events with violations")
def recordings_show(key: str, violations_only: bool):
    """Print formatted timeline for a session."""
    from datetime import datetime

    from agentlint.recorder import load_recording

    events = load_recording(key)
    if not events:
        click.echo("No recordings found.")
        return

    shown = 0
    violation_summary: dict[str, int] = {}
    for ev in events:
        violations = ev.get("violations", [])
        # Track violation summary
        for v in violations:
            rid = v.get("rule_id", "unknown")
            violation_summary[rid] = violation_summary.get(rid, 0) + 1

        if violations_only and not violations:
            continue

        ts = ev.get("ts", 0)
        dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        event_type = ev.get("event", "?")
        tool = ev.get("tool_name", "")
        v_str = f" [{len(violations)} violation(s)]" if violations else ""
        summary = ev.get("tool_summary", {})
        detail = ""
        if summary.get("command"):
            detail = f" $ {summary['command'][:80]}"
        elif summary.get("file_path"):
            detail = f" {summary['file_path']}"
        elif summary.get("url"):
            detail = f" {summary['url'][:80]}"
        elif summary.get("query"):
            detail = f" ? {summary['query'][:80]}"
        elif summary.get("subagent_type"):
            desc = summary.get("description", "")
            detail = f" [{summary['subagent_type']}] {desc[:60]}" if desc else f" [{summary['subagent_type']}]"
        elif summary.get("cell_index") is not None:
            detail = f" cell #{summary['cell_index']}"
        click.echo(f"  {dt}  {event_type:<20} {tool:<12}{v_str}{detail}")
        shown += 1

    click.echo(f"\n{shown} event(s) shown ({len(events)} total).")

    if violation_summary:
        click.echo("\nViolation summary:")
        for rule_id, count in sorted(violation_summary.items(), key=lambda x: x[1], reverse=True):
            click.echo(f"  {rule_id:<30} {count:>5}")


@recordings.command("stats")
@click.option("--last", "last_n", default=None, type=int, help="Only include last N sessions")
def recordings_stats(last_n: int | None):
    """Aggregate insights: top tools, top rules fired, patterns."""
    from agentlint.recorder import list_recordings as _list_recordings
    from agentlint.recorder import recording_stats as _recording_stats

    keys = None
    if last_n:
        recs = _list_recordings()
        recs.sort(key=lambda r: r["modified"], reverse=True)
        keys = [r["session_key"] for r in recs[:last_n]]

    stats = _recording_stats(keys=keys)

    if stats["total_events"] == 0:
        click.echo("No recordings found.")
        return

    click.echo(f"Sessions: {stats['sessions']}  |  Events: {stats['total_events']}")

    click.echo("\nTop tools:")
    for tool, count in stats["top_tools"][:10]:
        click.echo(f"  {tool:<20} {count:>5}")

    if stats["top_rules"]:
        click.echo("\nTop rules fired:")
        for rule, count in stats["top_rules"][:10]:
            click.echo(f"  {rule:<30} {count:>5}")

    click.echo("\nEvent types:")
    for et, count in stats["event_types"][:10]:
        click.echo(f"  {et:<20} {count:>5}")


@recordings.command("clear")
@click.option("--older-than", "older_than_days", default=None, type=int, help="Only delete recordings older than N days")
@click.confirmation_option(prompt="Delete recording files?")
def recordings_clear(older_than_days: int | None):
    """Delete recording files."""
    from agentlint.recorder import clear_recordings

    removed = clear_recordings(older_than_days=older_than_days)
    click.echo(f"Removed {removed} recording(s).")


if __name__ == "__main__":
    main()
