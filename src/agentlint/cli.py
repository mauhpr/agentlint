"""AgentLint CLI entry point."""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import click

from agentlint.agents_md import find_agents_md, generate_config, map_to_config, merge_with_existing, parse_agents_md
from agentlint.config import load_config
from agentlint.detector import detect_stack
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs import PACK_MODULES, load_custom_rules, load_rules
from agentlint.reporter import Reporter
from agentlint.session import cleanup_session, load_session, save_session
from agentlint.adapters._utils import resolve_command
from agentlint.adapters.claude import ClaudeAdapter
from agentlint.adapters.codex import CodexAdapter
from agentlint.adapters.continue_dev import ContinueAdapter
from agentlint.adapters.cursor import CursorAdapter
from agentlint.adapters.generic import GenericAdapter
from agentlint.adapters.gemini import GeminiAdapter
from agentlint.adapters.grok import GrokAdapter
from agentlint.adapters.kimi import KimiAdapter
from agentlint.adapters.mcp import MCPAdapter
from agentlint.adapters.openai_agents import OpenAIAgentsAdapter
from agentlint.formats.claude_hooks import ClaudeHookFormatter
from agentlint.formats.cursor_hooks import CursorHookFormatter
from agentlint.models import AgentEvent, to_hook_event
from agentlint.setup import merge_hooks, read_settings, remove_hooks, settings_path, write_settings
from agentlint.utils.git import get_changed_files, get_diff_files

logger = logging.getLogger("agentlint")


def _resolve_project_dir(project_dir: str | None = None) -> str:
    """Resolve project directory from explicit arg or environment."""
    return (
        project_dir
        or os.environ.get("AGENTLINT_PROJECT_DIR")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or os.getcwd()
    )


def _resolve_adapter(adapter_name: str | None = None) -> Any:
    """Resolve the agent adapter from explicit flag or environment detection.

    Priority:
    1. Explicit --adapter flag
    2. Agent-specific environment variables
    3. Default to Claude (backward compatibility)
    """
    _ADAPTERS: dict[str, Any] = {
        "claude": ClaudeAdapter,
        "codex": CodexAdapter,
        "continue": ContinueAdapter,
        "cursor": CursorAdapter,
        "gemini": GeminiAdapter,
        "generic": GenericAdapter,
        "grok": GrokAdapter,
        "kimi": KimiAdapter,
        "mcp": MCPAdapter,
        "openai": OpenAIAgentsAdapter,
    }

    if adapter_name:
        adapter_cls = _ADAPTERS.get(adapter_name)
        if adapter_cls is None:
            raise click.UsageError(
                f"Unknown adapter: {adapter_name}. Supported: {', '.join(_ADAPTERS)}"
            )
        return adapter_cls()

    # Auto-detect from environment
    if os.environ.get("KIMI_SESSION_ID") or os.environ.get("KIMI_PROJECT_DIR"):
        return KimiAdapter()
    if os.environ.get("GROK_SESSION_ID") or os.environ.get("GROK_PROJECT_DIR"):
        return GrokAdapter()
    if os.environ.get("GEMINI_SESSION_ID") or os.environ.get("GEMINI_PROJECT_DIR"):
        return GeminiAdapter()
    if os.environ.get("CODEX_SESSION_ID") or os.environ.get("CODEX_PROJECT_DIR"):
        return CodexAdapter()
    if os.environ.get("CONTINUE_SESSION_ID") or os.environ.get("CONTINUE_PROJECT_DIR"):
        return ContinueAdapter()
    if os.environ.get("CURSOR_SESSION_ID") or os.environ.get("CURSOR_PROJECT_DIR"):
        return CursorAdapter()
    if os.environ.get("OPENAI_RUN_ID") or os.environ.get("OPENAI_THREAD_ID"):
        return OpenAIAgentsAdapter()
    if os.environ.get("MCP_SESSION_ID"):
        return MCPAdapter()
    # Default to Claude for backward compatibility
    return ClaudeAdapter()


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
@click.option("--adapter", default=None, help="Agent adapter (claude, cursor). Auto-detected if not set.")
@click.option("--format", "output_format", default=None, help="Output format override (claude_hooks, cursor_hooks)")
def check(event: str, project_dir: str | None, adapter: str | None, output_format: str | None):
    """Evaluate rules against a tool call from stdin."""
    adapter_obj = _resolve_adapter(adapter)
    project_dir = _resolve_project_dir(project_dir)

    # Translate event via adapter (supports both native and generic event names)
    try:
        agent_event = adapter_obj.translate_event(event)
    except ValueError:
        # Fall back to direct HookEvent parsing for backward compatibility
        agent_event = AgentEvent.from_string(event)
    hook_event = to_hook_event(agent_event)

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
        agent_platform=adapter_obj.platform_name,
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
                agent_platform=adapter_obj.platform_name,
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
                agent_platform=adapter_obj.platform_name,
            )

    # Resolve project-specific packs for monorepo
    effective_config = config
    if context.file_path and config.projects:
        effective_packs = config.resolve_packs_for_file(context.file_path, project_dir)
        effective_config = config.with_packs(effective_packs)

    engine = Engine(config=effective_config, rules=rules)
    start_time = time.time()
    result = engine.evaluate(context)
    elapsed_ms = (time.time() - start_time) * 1000

    # Track hook timing in session state
    timing = session_state.setdefault("_hook_timing", {"total_ms": 0.0, "count": 0})
    timing["total_ms"] += elapsed_ms
    timing["count"] += 1

    # Apply inline ignore directives (# agentlint:ignore-file, etc.).
    # Pass file_path + session_state so reasons surface in the summary.
    from agentlint.filters import filter_inline_ignores
    result.violations = filter_inline_ignores(
        result.violations,
        context.file_content,
        file_path=context.file_path,
        session_state=session_state,
    )

    # Track cumulative violation counts for session summary
    vlog = session_state.setdefault("violation_log", {
        "total_evaluations": 0,
        "total_blocked": 0,
        "total_warnings": 0,
        "total_info": 0,
        "rule_violations": {},
    })
    vlog["total_evaluations"] += 1
    for v in result.violations:
        if v.severity == Severity.ERROR:
            vlog["total_blocked"] += 1
        elif v.severity == Severity.WARNING:
            vlog["total_warnings"] += 1
        else:
            vlog["total_info"] += 1
        rv = vlog["rule_violations"]
        rv[v.rule_id] = rv.get(v.rule_id, 0) + 1

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

    # Determine formatter: adapter default or explicit --format override
    formatter = adapter_obj.formatter
    if output_format == "claude_hooks":
        formatter = ClaudeHookFormatter()
    elif output_format == "cursor_hooks":
        formatter = CursorHookFormatter()

    reporter = Reporter(
        violations=result.violations,
        rules_evaluated=result.rules_evaluated,
        formatter=formatter,
    )
    if event == "SubagentStart" or event == "subagentStart":
        output = reporter.format_subagent_start_output()
    else:
        output = reporter.format_hook_output(event=agent_event)
    if output:
        click.echo(output)

    sys.exit(reporter.exit_code(event=event))


@main.command()
@click.option("--diff", default=None, help="Git diff range (e.g., origin/main...HEAD)")
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]))
def ci(diff: str | None, project_dir: str | None, output_format: str):
    """Scan changed files and report violations for CI pipelines."""
    project_dir = _resolve_project_dir(project_dir)

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
    project_dir = _resolve_project_dir(project_dir)
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
@click.option("--summary", is_flag=True, help="Show cumulative session summary dashboard")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]),
              help="Output format (only applies with --summary)")
@click.option("--adapter", default=None, help="Agent adapter (claude, cursor). Auto-detected if not set.")
def report(project_dir: str | None, summary: bool, output_format: str, adapter: str | None):
    """Generate session summary report (for Stop event)."""
    project_dir = _resolve_project_dir(project_dir)
    adapter_obj = _resolve_adapter(adapter)

    # Only consume stdin if not in --summary mode (Stop hook pipes JSON)
    if not summary:
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

    # --summary: show cumulative dashboard and exit
    if summary:
        reporter = Reporter(violations=[], rules_evaluated=0)
        click.echo(reporter.format_session_summary(
            session_state=session_state,
            output_format=output_format,
        ))
        return

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
@click.argument("platform", required=False, default="claude")
@click.option("--global", "scope", flag_value="user", help="Install to user settings")
@click.option(
    "--project", "scope", flag_value="project", default=True, help="Install to project settings (default)"
)
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--dry-run", is_flag=True, help="Show what would be written without modifying files")
def setup(platform: str, scope: str, project_dir: str | None, dry_run: bool):
    """Install AgentLint hooks into agent settings."""
    project_dir = _resolve_project_dir(project_dir)

    _ADAPTERS: dict[str, Any] = {
        "claude": ClaudeAdapter,
        "cursor": CursorAdapter,
        "openai": OpenAIAgentsAdapter,
        "mcp": MCPAdapter,
        "generic": GenericAdapter,
    }
    adapter_cls = _ADAPTERS.get(platform)
    if adapter_cls is None:
        raise click.UsageError(
            f"Unknown platform: {platform}. Supported: {', '.join(_ADAPTERS)}"
        )
    adapter = adapter_cls()

    agentlint_cmd = resolve_command()
    click.echo(f"Resolved agentlint: {agentlint_cmd}")

    adapter.install_hooks(project_dir, scope=scope, dry_run=dry_run, cmd=agentlint_cmd)

    click.echo(f"Installed AgentLint hooks for {platform}")

    # Also create agentlint.yml if it doesn't exist
    config_path = os.path.join(project_dir, "agentlint.yml")
    if not dry_run and not os.path.exists(config_path):
        ctx = click.Context(init)
        ctx.invoke(init, project_dir=project_dir)


@main.command("list-rules")
@click.option("--pack", default=None, help="Filter rules by pack name")
@click.option("--project-dir", default=None, help="Project directory")
def list_rules(pack: str | None, project_dir: str | None):
    """List all available rules."""
    project_dir = _resolve_project_dir(project_dir)

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
    click.echo(f"{'Rule ID':<30} {'Pack':<12} {'Event':<20} {'Severity':<10} Description")
    click.echo("-" * 106)

    for rule in rules:
        event_str = ", ".join(e.value for e in rule.events) if rule.events else "—"
        click.echo(
            f"{rule.id:<30} {rule.pack:<12} {event_str:<20} {rule.severity.value:<10} {rule.description}"
        )

    click.echo(f"\n{len(rules)} rules total.")


@main.command()
@click.option("--project-dir", default=None, help="Project directory")
def status(project_dir: str | None):
    """Show AgentLint status for the current project."""
    from importlib.metadata import version as get_version

    project_dir = _resolve_project_dir(project_dir)

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
    project_dir = _resolve_project_dir(project_dir)
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

    # Check hooks registered (Claude)
    claude_hook_path = settings_path("project", project_dir)
    claude_hook_data = read_settings(claude_hook_path)
    claude_hooks_installed = "hooks" in claude_hook_data and any(
        "agentlint" in str(claude_hook_data["hooks"].get(evt, []))
        for evt in ("PreToolUse", "PostToolUse", "Stop")
    )

    # Check hooks registered (Cursor)
    cursor_hook_path = Path(project_dir) / ".cursor" / "hooks.json"
    cursor_hooks_installed = False
    if cursor_hook_path.exists():
        try:
            cursor_hook_data = json.loads(cursor_hook_path.read_text())
            cursor_hooks_installed = "hooks" in cursor_hook_data and any(
                "agentlint" in str(cursor_hook_data["hooks"].get(evt, []))
                for evt in ("preToolUse", "postToolUse", "stop")
            )
        except (json.JSONDecodeError, OSError):
            pass

    if claude_hooks_installed and cursor_hooks_installed:
        checks_ok.append("Hooks: installed for both Claude and Cursor")
    elif claude_hooks_installed:
        checks_ok.append("Hooks: installed in .claude/settings.json")
    elif cursor_hooks_installed:
        checks_ok.append("Hooks: installed in .cursor/hooks.json")
    else:
        issues.append("Hooks: not installed. Run 'agentlint setup claude' or 'agentlint setup cursor' to install.")

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
        _TOOL_RECIPES = {
            # Python
            "ruff": [
                "ruff check {file.path} --output-format=concise",
                "ruff format {file.path} --check --diff",
            ],
            "mypy": ["mypy {file.path}"],
            "black": ["black --check {file.path}"],
            # JavaScript / TypeScript
            "eslint": ["eslint {file.path}"],
            "prettier": ["prettier --check {file.path}"],
            "tsc": ["tsc --noEmit"],
            "biome": ["biome check {file.path}"],
            # Go
            "golangci-lint": ["golangci-lint run {file.path}"],
            # Rust
            "clippy-driver": ["cargo clippy -- -D warnings"],
            # Ruby
            "rubocop": ["rubocop {file.path}"],
        }
        for tool, recipes in _TOOL_RECIPES.items():
            if shutil.which(tool):
                recipe_str = ", ".join(f"`{r}`" for r in recipes)
                checks_ok.append(f"CLI recipe: {tool} found — consider adding to cli-integration ({recipe_str})")

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
@click.option("--remove", "remove_id", default=None, help="Remove a single suppression")
def suppress(rule_id: str | None, list_mode: bool, clear: bool, remove_id: str | None):
    """Suppress a warning rule for the rest of the session."""
    # Mutual exclusion check
    actions = sum([bool(rule_id), list_mode, clear, bool(remove_id)])
    if actions > 1:
        raise click.UsageError("RULE_ID, --list, --clear, and --remove are mutually exclusive.")

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
    elif remove_id:
        if remove_id in suppressed:
            suppressed.remove(remove_id)
            save_session(session_state)
            click.echo(f"Removed suppression for '{remove_id}'.")
        else:
            click.echo(f"'{remove_id}' is not suppressed.")
    elif rule_id:
        if rule_id not in suppressed:
            suppressed.append(rule_id)
            save_session(session_state)
            click.echo(f"Suppressed '{rule_id}' for this session.")
        else:
            click.echo(f"'{rule_id}' is already suppressed.")
    else:
        click.echo("Usage: agentlint suppress RULE_ID | --list | --clear | --remove RULE_ID")


@main.command("import-agents-md")
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--dry-run", is_flag=True, help="Preview config without writing")
@click.option("--merge", "merge_mode", is_flag=True, help="Merge with existing agentlint.yml")
def import_agents_md(project_dir: str | None, dry_run: bool, merge_mode: bool):
    """Import conventions from AGENTS.md into AgentLint config."""
    project_dir = _resolve_project_dir(project_dir)

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
@click.argument("platform", required=False, default="claude")
@click.option("--global", "scope", flag_value="user", help="Remove from user settings")
@click.option(
    "--project", "scope", flag_value="project", default=True, help="Remove from project settings (default)"
)
@click.option("--project-dir", default=None, help="Project directory")
def uninstall(platform: str, scope: str, project_dir: str | None):
    """Remove AgentLint hooks from agent settings."""
    project_dir = _resolve_project_dir(project_dir)

    _ADAPTERS: dict[str, Any] = {
        "claude": ClaudeAdapter,
        "cursor": CursorAdapter,
        "openai": OpenAIAgentsAdapter,
        "mcp": MCPAdapter,
        "generic": GenericAdapter,
    }
    adapter_cls = _ADAPTERS.get(platform)
    if adapter_cls is None:
        raise click.UsageError(
            f"Unknown platform: {platform}. Supported: {', '.join(_ADAPTERS)}"
        )
    adapter = adapter_cls()

    adapter.uninstall_hooks(project_dir, scope=scope)
    click.echo(f"Removed AgentLint hooks for {platform}")


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
