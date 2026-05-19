"""AgentLint CLI entry point."""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

import click

from agentlint import __version__
from agentlint.agents_md import find_agents_md, generate_config, map_to_config, merge_with_existing, parse_agents_md
from agentlint.config import load_config
from agentlint.detector import detect_stack
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs import PACK_MODULES, load_custom_rules, load_installed_rules, load_project_rules, load_rules
from agentlint.reporter import Reporter
from agentlint.session import cleanup_session, load_session, save_session
from agentlint.adapters._utils import resolve_command
from agentlint.adapters import get_adapter
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

_TOML_SECTION_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*(?:#.*)?$")
_CODEX_HOOKS_KEY_RE = re.compile(r"^(\s*)codex_hooks\s*=.*$")
_HOOKS_KEY_RE = re.compile(r"^(\s*)hooks\s*=.*$")
_AGENTCHUTE_ENV_BEGIN = "# >>> agentlint agentchute >>>"
_AGENTCHUTE_ENV_END = "# <<< agentlint agentchute <<<"

_SUPPORTED_ADAPTERS = (
    "claude",
    "cursor",
    "kimi",
    "grok",
    "gemini",
    "codex",
    "continue",
    "openai",
    "mcp",
    "generic",
)
_HOOK_PLATFORMS = ("claude", "cursor", "codex", "gemini", "continue", "kimi", "grok")


def _resolve_project_dir(project_dir: str | None = None) -> str:
    """Resolve project directory from explicit arg or environment."""
    return (
        project_dir
        or os.environ.get("AGENTLINT_PROJECT_DIR")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or os.getcwd()
    )


def _agentchute_policy_metadata() -> dict:
    """Return safe cached-policy metadata for AgentChute event visibility."""
    try:
        from agentlint.agentchute.policy import policy_status
        status = policy_status()
    except Exception:
        logger.debug("Failed to read AgentChute policy status", exc_info=True)
        return {"cached": False, "version": None, "updated_at": None, "error": "unavailable"}
    return {
        "cached": bool(status.get("cached")),
        "version": status.get("version"),
        "updated_at": status.get("updated_at"),
        "error": status.get("error"),
    }


def _codex_hooks_enabled() -> bool:
    """Return whether current Codex native hooks are enabled in config.toml."""
    config_path = Path.home() / ".codex" / "config.toml"
    try:
        text = config_path.read_text()
    except OSError:
        return False

    try:
        config = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return False

    features = config.get("features")
    if not isinstance(features, dict):
        return False
    return features.get("hooks") is True


def _enable_codex_hooks() -> Path:
    """Enable Codex hooks in ~/.codex/config.toml without corrupting TOML tables."""
    config_path = Path.home() / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        text = config_path.read_text()
    except OSError:
        text = ""

    lines = text.splitlines()
    output: list[str] = []
    current_section: str | None = None
    features_start: int | None = None
    features_end: int | None = None
    features_hooks_index: int | None = None

    for line in lines:
        section_match = _TOML_SECTION_RE.match(line)
        if section_match:
            if current_section == "features" and features_end is None:
                features_end = len(output)
            current_section = section_match.group(1).strip()
            if current_section == "features":
                features_start = len(output)
            output.append(line)
            continue

        if _CODEX_HOOKS_KEY_RE.match(line):
            # Drop the deprecated key from any table. Codex now expects
            # [features].hooks, and orphan/nested codex_hooks keys can break
            # schema loading.
            continue

        if current_section == "features" and _HOOKS_KEY_RE.match(line):
            features_hooks_index = len(output)
            output.append("hooks = true")
            continue

        output.append(line)

    if current_section == "features" and features_end is None:
        features_end = len(output)

    if features_hooks_index is None:
        if features_start is None:
            if output and output[-1].strip():
                output.append("")
            output.extend(["[features]", "hooks = true"])
        else:
            insert_at = features_end if features_end is not None else len(output)
            output.insert(insert_at, "hooks = true")

    config_path.write_text("\n".join(output) + "\n")
    return config_path


def _detect_update_command() -> tuple[str, list[str]]:
    """Return the best-effort installer command that updates this AgentLint install."""
    override = os.environ.get("AGENTLINT_UPDATE_COMMAND")
    if override:
        return "override", shlex.split(override)

    executable = str(Path(sys.executable).resolve())
    lowered = executable.lower()

    if "pipx" in lowered and shutil.which("pipx"):
        return "pipx", ["pipx", "upgrade", "agentlint"]

    if "uv" in lowered and shutil.which("uv"):
        return "uv tool", ["uv", "tool", "install", "--upgrade", "agentlint"]

    if os.environ.get("VIRTUAL_ENV"):
        return "pip", [sys.executable, "-m", "pip", "install", "--upgrade", "agentlint"]

    if shutil.which("uv") and (
        ".local/share/uv/tools/agentlint" in lowered
        or ".local/bin/agentlint" in str(Path(resolve_command()).resolve()).lower()
    ):
        return "uv tool", ["uv", "tool", "install", "--upgrade", "agentlint"]

    return "pip", [sys.executable, "-m", "pip", "install", "--upgrade", "agentlint"]


def _default_shell_profile() -> Path:
    """Choose the shell startup file where AgentChute env vars should be persisted."""
    override = os.environ.get("AGENTLINT_SHELL_PROFILE")
    if override:
        return Path(override).expanduser()

    shell = Path(os.environ.get("SHELL", "")).name
    home = Path.home()
    if shell == "zsh":
        return home / ".zshrc"
    if shell == "bash":
        return home / ".bashrc"
    return home / ".profile"


def _agentchute_env_block(*, api_url: str, team_key: str) -> str:
    return "\n".join(
        [
            _AGENTCHUTE_ENV_BEGIN,
            f"export AGENTCHUTE_API_URL={shlex.quote(api_url)}",
            f"export AGENTCHUTE_LICENSE_KEY={shlex.quote(team_key)}",
            "export AGENTCHUTE_ENABLED=true",
            _AGENTCHUTE_ENV_END,
        ]
    )


def _persist_agentchute_env(*, api_url: str, team_key: str, profile: Path | None = None) -> Path:
    """Write or replace the managed AgentChute env block in a shell profile."""
    profile = profile or _default_shell_profile()
    profile.parent.mkdir(parents=True, exist_ok=True)

    try:
        text = profile.read_text()
    except OSError:
        text = ""

    block = _agentchute_env_block(api_url=api_url, team_key=team_key)
    pattern = re.compile(
        rf"{re.escape(_AGENTCHUTE_ENV_BEGIN)}.*?{re.escape(_AGENTCHUTE_ENV_END)}",
        re.DOTALL,
    )
    if pattern.search(text):
        updated = pattern.sub(block, text)
    else:
        suffix = "" if not text or text.endswith("\n") else "\n"
        updated = f"{text}{suffix}\n{block}\n"

    profile.write_text(updated)
    return profile


def _ensure_agentchute_enabled_config(config_path: Path) -> None:
    """Enable AgentChute in agentlint.yml without persisting the license key."""
    if not config_path.exists():
        return

    text = config_path.read_text()
    lines = text.splitlines()
    if not any(line.strip() == "agentchute:" for line in lines):
        updated = text.rstrip() + "\n\nagentchute:\n  enabled: true\n"
        config_path.write_text(updated)
        return

    output: list[str] = []
    in_agentchute = False
    saw_enabled = False
    for line in lines:
        stripped = line.strip()
        if stripped == "agentchute:":
            in_agentchute = True
            saw_enabled = False
            output.append(line)
            continue
        if in_agentchute and line and not line.startswith((" ", "\t", "#")):
            if not saw_enabled:
                output.append("  enabled: true")
            in_agentchute = False
        elif in_agentchute and stripped and not stripped.startswith("#") and not saw_enabled and not stripped.startswith("enabled:"):
            output.append("  enabled: true")
            saw_enabled = True
        if in_agentchute and stripped.startswith("enabled:"):
            output.append("  enabled: true")
            saw_enabled = True
            continue
        output.append(line)

    if in_agentchute and not saw_enabled:
        output.append("  enabled: true")

    config_path.write_text("\n".join(output) + "\n")


def _platform_hook_file(platform: str, project_dir: str) -> Path | None:
    base = Path(project_dir)
    if platform == "claude":
        return base / ".claude" / "settings.json"
    if platform == "cursor":
        return base / ".cursor" / "hooks.json"
    if platform == "codex":
        return base / ".codex" / "hooks.json"
    if platform == "gemini":
        return base / ".gemini" / "settings.json"
    if platform == "continue":
        return base / ".continue" / "settings.json"
    if platform == "kimi":
        return base / ".kimi" / "config.toml"
    if platform == "grok":
        return base / ".grok" / "settings.json"
    return None


def _agentlint_hooks_present(path: Path | None) -> bool:
    if path is None or not path.exists():
        return False
    try:
        return "agentlint" in path.read_text(encoding="utf-8", errors="ignore").lower()
    except OSError:
        return False


def _hook_status(platform: str, project_dir: str) -> tuple[str, str]:
    path = _platform_hook_file(platform, project_dir)
    if path is None:
        return "unsupported", ""
    if not path.exists():
        return "missing", str(path)
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return "unreadable", str(path)
    if "agentlint" not in text.lower():
        return "custom", str(path)
    resolved = resolve_command()
    if resolved not in text and re.search(r"/[^\s\"']*agentlint(?:\s|$)", text):
        return "stale", str(path)
    return "installed", str(path)


def _detected_agent_platforms(project_dir: str) -> list[str]:
    """Detect likely coding-agent configs in the current project/environment."""
    detected: list[str] = []
    for platform in _HOOK_PLATFORMS:
        path = _platform_hook_file(platform, project_dir)
        if path and path.exists():
            detected.append(platform)

    env_markers = {
        "claude": ("CLAUDE_PROJECT_DIR", "CLAUDE_SESSION_ID"),
        "cursor": ("CURSOR_PROJECT_DIR", "CURSOR_SESSION_ID"),
        "codex": ("CODEX_PROJECT_DIR", "CODEX_SESSION_ID"),
        "gemini": ("GEMINI_PROJECT_DIR", "GEMINI_SESSION_ID"),
        "continue": ("CONTINUE_PROJECT_DIR", "CONTINUE_SESSION_ID"),
        "kimi": ("KIMI_PROJECT_DIR", "KIMI_SESSION_ID"),
        "grok": ("GROK_PROJECT_DIR", "GROK_SESSION_ID"),
    }
    for platform, markers in env_markers.items():
        if platform not in detected and any(os.environ.get(marker) for marker in markers):
            detected.append(platform)

    if not detected:
        detected.append("codex")
    return detected


def _resolve_onboard_platforms(raw_platforms: tuple[str, ...], project_dir: str) -> list[str]:
    if not raw_platforms or "auto" in raw_platforms:
        return _detected_agent_platforms(project_dir)
    if "all" in raw_platforms:
        return list(_HOOK_PLATFORMS)

    platforms: list[str] = []
    for item in raw_platforms:
        for platform in item.split(","):
            platform = platform.strip()
            if not platform:
                continue
            if platform not in _HOOK_PLATFORMS:
                raise click.UsageError(
                    f"Unknown hook platform: {platform}. Supported: {', '.join(_HOOK_PLATFORMS)}, auto, all"
                )
            if platform not in platforms:
                platforms.append(platform)
    return platforms


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
@click.version_option(__version__, prog_name="agentlint", message="agentlint %(version)s")
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
    rules = load_project_rules(config, project_dir)
    try:
        from agentlint.agentchute.policy import missing_required_packs
        missing_packs = missing_required_packs()
        for name in missing_packs:
            click.echo(
                f"AgentChute policy requires missing custom pack '{name}'. "
                "Install it to enable all org rules.",
                err=True,
            )
    except Exception:
        logger.debug("Failed to inspect AgentChute required packs", exc_info=True)

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
    recording_event = None
    try:
        from agentlint.recorder import is_recording_enabled
        from agentlint.agentchute import is_agentchute_enabled
        # Build the event payload once; reused for the local recording
        # AND the optional AgentChute real-time POST so the two paths see the
        # exact same data. Privacy contract: no raw file content, no raw
        # prompt — summarize_tool_input enforces that for both paths.
        recording_needed = is_recording_enabled(config)
        agentchute_needed = is_agentchute_enabled(config)
        if recording_needed or agentchute_needed:
            from agentlint.recorder import summarize_tool_input
            from agentlint.session import _session_key
            recording_event = {
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
                "agent_platform": adapter_obj.platform_name,
                "agentlint_version": __version__,
                "policy": _agentchute_policy_metadata(),
            }
            session_key = _session_key()
            if recording_needed:
                from agentlint.recorder import append_event
                append_event(recording_event, key=session_key)
            if agentchute_needed:
                from agentlint.agentchute.queue import enqueue_event, trigger_background_flush
                enqueue_event(recording_event, session_key=session_key, config=config)
                trigger_background_flush(config=config)
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
    rules = load_project_rules(config, project_dir)
    try:
        from agentlint.agentchute.policy import missing_required_packs
        missing_packs = missing_required_packs()
    except Exception:
        missing_packs = []
    if missing_packs:
        message = {
            "violations": [
                {
                    "rule_id": "agentchute-required-pack",
                    "message": f"Missing required AgentChute custom pack: {name}",
                    "severity": "error",
                    "file_path": None,
                    "line": None,
                    "suggestion": f"Install {name} in CI before running agentlint.",
                }
                for name in missing_packs
            ],
            "files_scanned": 0,
            "rules_evaluated": 0,
        }
        if output_format == "json":
            click.echo(json.dumps(message))
        else:
            for violation in message["violations"]:
                click.echo(f"?  [{violation['rule_id']}] ERROR  {violation['message']}")
                click.echo(f"  -> {violation['suggestion']}")
        sys.exit(1)

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
            for group in _group_ci_violations(all_violations):
                if len(group) == 1:
                    v = group[0]
                    sev = v.severity.value.upper()
                    loc = f"{v.file_path}" if v.file_path else "?"
                    click.echo(f"{loc}  [{v.rule_id}] {sev}  {v.message}")
                    if v.suggestion:
                        click.echo(f"  → {v.suggestion}")
                    click.echo()
                    continue

                first = group[0]
                sev = first.severity.value.upper()
                loc = f"{first.file_path}" if first.file_path else "?"
                click.echo(f"{loc}  [{first.rule_id}] {sev}  {len(group)} findings")
                for v in group:
                    line = f"line {v.line}: " if v.line is not None else ""
                    click.echo(f"  - {line}{v.message}")
                suggestions = sorted({v.suggestion for v in group if v.suggestion})
                if len(suggestions) == 1:
                    click.echo(f"  → {suggestions[0]}")
                click.echo()
            click.echo(
                f"{len(all_violations)} violation(s) "
                f"({len(errors)} error, {len(warnings)} warning, {len(infos)} info) "
                f"in {len(changed_files)} files"
            )

    sys.exit(1 if has_errors else 0)


def _group_ci_violations(violations: list) -> list[list]:
    """Group repeated text CI findings by file, rule, and severity."""
    grouped: list[list] = []
    index: dict[tuple, list] = {}
    for violation in violations:
        key = (violation.file_path, violation.rule_id, violation.severity.value)
        if key not in index:
            index[key] = []
            grouped.append(index[key])
        index[key].append(violation)
    return grouped


@main.command()
@click.option("--project-dir", default=None, help="Project directory")
@click.option(
    "--team-key",
    default=None,
    help=(
        "AgentChute team key. Enables AgentChute in config and prints the env vars "
        "to add to your shell or AI tool settings; the secret is not written to disk."
    ),
)
def init(project_dir: str | None, team_key: str | None):
    """Initialize AgentLint config in the project."""
    project_dir = _resolve_project_dir(project_dir)
    packs = detect_stack(project_dir)

    pack_lines = "\n".join(f"  - {p}" for p in packs)
    agentchute_enabled = "true" if team_key else "false"
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

agentchute:
  enabled: {agentchute_enabled}  # opt-in cloud dashboard and hybrid security feeds

# custom_rules_dir: .agentlint/rules/
# Custom rules with pack = "mypack" activate when "mypack" is listed in packs above
"""
    config_path = os.path.join(project_dir, "agentlint.yml")
    with open(config_path, "w") as f:
        f.write(config_content)

    click.echo(f"Created {config_path}")
    click.echo(f"Detected packs: {', '.join(packs)}")
    if team_key:
        from agentlint.agentchute.client import DEFAULT_API_URL, ENV_AGENTCHUTE_API_URL

        api_url = os.environ.get(ENV_AGENTCHUTE_API_URL, DEFAULT_API_URL)
        click.echo("")
        click.echo("AgentChute enabled. Add these env vars to your shell or AI tool settings:")
        click.echo(f"export AGENTCHUTE_API_URL={api_url}")
        click.echo(f"export AGENTCHUTE_LICENSE_KEY={team_key}")
        click.echo("export AGENTCHUTE_ENABLED=true")


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
    rules = load_project_rules(config, project_dir)

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
        from agentlint.agentchute import is_agentchute_enabled
        recording_needed = is_recording_enabled(config)
        agentchute_needed = is_agentchute_enabled(config)
        if recording_needed or agentchute_needed:
            from agentlint.session import _session_key
            entry = {
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
            }
            session_key = _session_key()
            if recording_needed:
                from agentlint.recorder import append_event
                append_event(entry, key=session_key)
            if agentchute_needed:
                from agentlint.agentchute.queue import enqueue_event, trigger_background_flush
                enqueue_event(entry, session_key=session_key, config=config)
                trigger_background_flush(config=config)
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

    if platform not in _SUPPORTED_ADAPTERS:
        raise click.UsageError(
            f"Unknown platform: {platform}. Supported: {', '.join(_SUPPORTED_ADAPTERS)}"
        )
    adapter = get_adapter(platform)

    agentlint_cmd = resolve_command()
    click.echo(f"Resolved agentlint: {agentlint_cmd}")

    adapter.install_hooks(project_dir, scope=scope, dry_run=dry_run, cmd=agentlint_cmd)

    click.echo(f"Installed AgentLint hooks for {platform}")

    if platform == "codex" and not dry_run:
        if _codex_hooks_enabled():
            click.echo("Codex hooks are enabled in ~/.codex/config.toml.")
        else:
            config_path = _enable_codex_hooks()
            click.echo(f"Enabled Codex hooks in {config_path}.")
            click.echo("Set [features].hooks = true.")
        click.echo("Restart Codex from the terminal where your AgentLint/AgentChute env vars are set.")

    # Also create agentlint.yml if it doesn't exist
    config_path = os.path.join(project_dir, "agentlint.yml")
    if not dry_run and not os.path.exists(config_path):
        ctx = click.Context(init)
        ctx.invoke(init, project_dir=project_dir)


@main.command()
@click.option("--dry-run", is_flag=True, help="Print the detected update command without running it")
def update(dry_run: bool):
    """Update AgentLint using the detected installer."""
    kind, command = _detect_update_command()
    click.echo(f"Detected install: {kind}")
    click.echo("Command to run: " + " ".join(shlex.quote(part) for part in command))
    if dry_run:
        return
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise click.ClickException(
            "Installer failed with exit code " + str(result.returncode)
        )


@main.command()
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--platform", "platforms", multiple=True, help="Coding agent to configure. Repeat or use comma list. Use auto/all.")
@click.option("--team-key", default=None, help="AgentChute license key")
@click.option("--api-url", default=None, help="AgentChute API URL")
@click.option("--no-update", is_flag=True, help="Skip AgentLint self-update")
@click.option("--yes", is_flag=True, help="Accept defaults without prompts")
@click.option("--open-dashboard", is_flag=True, help="Open the AgentChute dashboard when finished")
@click.option("--dry-run", is_flag=True, help="Show actions without writing files")
def onboard(
    project_dir: str | None,
    platforms: tuple[str, ...],
    team_key: str | None,
    api_url: str | None,
    no_update: bool,
    yes: bool,
    open_dashboard: bool,
    dry_run: bool,
):
    """Guided setup: update, configure AgentChute, install hooks, and smoke test."""
    from agentlint.agentchute.client import DEFAULT_API_URL

    project_dir = _resolve_project_dir(project_dir)
    selected = _resolve_onboard_platforms(platforms, project_dir)
    api_url = api_url or os.environ.get("AGENTCHUTE_API_URL") or DEFAULT_API_URL

    click.echo("AgentLint onboarding")
    click.echo(f"Project: {project_dir}")
    click.echo(f"Coding agents: {', '.join(selected)}")

    if not no_update:
        kind, command = _detect_update_command()
        click.echo(
            "Installer: "
            + kind
            + " -> "
            + " ".join(shlex.quote(part) for part in command)
        )
        if not dry_run and (yes or click.confirm("Update AgentLint now?", default=False)):
            result = subprocess.run(command, check=False)
            if result.returncode != 0:
                raise click.ClickException("AgentLint update failed")

    if team_key is None and not yes and not dry_run:
        team_key = click.prompt("AgentChute license key", default=os.environ.get("AGENTCHUTE_LICENSE_KEY", ""), hide_input=True)
        team_key = team_key.strip() or None

    config_path = Path(project_dir) / "agentlint.yml"
    if dry_run:
        click.echo(f"Would create/update {config_path}")
    else:
        if not config_path.exists():
            ctx = click.Context(init)
            ctx.invoke(init, project_dir=project_dir, team_key=team_key)
        elif team_key:
            _ensure_agentchute_enabled_config(config_path)
            click.echo(f"Updated {config_path}: AgentChute enabled")

    if team_key:
        if dry_run:
            click.echo(f"Would persist AgentChute env vars to {_default_shell_profile()}")
        else:
            profile = _persist_agentchute_env(api_url=api_url, team_key=team_key)
            os.environ["AGENTCHUTE_API_URL"] = api_url
            os.environ["AGENTCHUTE_LICENSE_KEY"] = team_key
            os.environ["AGENTCHUTE_ENABLED"] = "true"
            click.echo(f"Saved AgentChute env vars to {profile}")

    for platform in selected:
        state, path = _hook_status(platform, project_dir)
        action = "repairing" if state == "stale" else "installing" if state == "missing" else "refreshing"
        click.echo(f"{platform}: {action} hooks")
        if not dry_run:
            get_adapter(platform).install_hooks(project_dir, scope="project", cmd=resolve_command())
            if platform == "codex":
                _enable_codex_hooks()
        elif path:
            click.echo(f"  would write {path}")

    if not dry_run:
        ctx = click.Context(agentlint_test)
        ctx.invoke(agentlint_test, project_dir=project_dir, flush=True)

    if open_dashboard and not dry_run:
        import webbrowser
        webbrowser.open("http://localhost:3001/dashboard" if "localhost" in api_url else "https://app.agentchute.com/dashboard")


@main.command("setup-agent")
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--platform", "platforms", multiple=True, help="Agent to add. Defaults to detected agents.")
@click.option("--all", "all_platforms", is_flag=True, help="Install hooks for all supported coding agents")
@click.option("--yes", is_flag=True, help="Install without confirmation")
def setup_agent(project_dir: str | None, platforms: tuple[str, ...], all_platforms: bool, yes: bool):
    """Detect and add AgentLint hooks for coding agents."""
    project_dir = _resolve_project_dir(project_dir)
    selected = list(_HOOK_PLATFORMS) if all_platforms else _resolve_onboard_platforms(platforms or ("auto",), project_dir)
    click.echo("Detected coding-agent hook state:")
    for platform in _HOOK_PLATFORMS:
        state, _ = _hook_status(platform, project_dir)
        marker = "✓" if state == "installed" else "!" if state == "stale" else "○"
        click.echo(f"  {marker} {platform:<8} {state}")
    if not yes and not click.confirm(f"Install/repair hooks for: {', '.join(selected)}?", default=True):
        return
    for platform in selected:
        get_adapter(platform).install_hooks(project_dir, scope="project", cmd=resolve_command())
        if platform == "codex":
            _enable_codex_hooks()
        click.echo(f"Installed AgentLint hooks for {platform}")


@main.command("test")
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--flush", is_flag=True, help="Flush the AgentChute queue after enqueueing the test event")
def agentlint_test(project_dir: str | None, flush: bool):
    """Run a safe local and AgentChute end-to-end smoke test."""
    from agentlint.agentchute.queue import enqueue_event, flush_queue
    from agentlint.session import _session_key

    project_dir = _resolve_project_dir(project_dir)
    config = load_config(project_dir)
    rules = load_project_rules(config, project_dir)
    engine = Engine(config=config, rules=rules)
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": ".env", "content": "AGENTLINT_TEST_SECRET=sk-test-agentlint-smoke"},
        project_dir=project_dir,
        config=config.rules,
    )
    result = engine.evaluate(context)
    blocked = result.is_blocking
    click.echo(f"Local rule smoke: {'blocked risky fixture' if blocked else 'no block'} ({result.rules_evaluated} rules)")

    event = {
        "v": 1,
        "ts": time.time(),
        "event": "AgentLintTest",
        "tool_name": "agentlint",
        "violations": [{"rule_id": v.rule_id, "severity": v.severity.value} for v in result.violations],
        "rules_evaluated": result.rules_evaluated,
        "is_blocking": blocked,
        "project_dir": project_dir,
        "agent_platform": "agentlint-test",
        "agentlint_version": __version__,
        "policy": _agentchute_policy_metadata(),
    }
    event_id = enqueue_event(event, session_key=_session_key(), config=config)
    if event_id:
        click.echo(f"AgentChute queue: wrote test event {event_id}")
    else:
        click.echo("AgentChute queue: skipped (not enabled or missing key)")
    if flush:
        flush_result = flush_queue(max_events=10)
        if flush_result.aborted_reason:
            click.echo(f"AgentChute upload: skipped ({flush_result.aborted_reason})")
        elif flush_result.locked:
            click.echo("AgentChute upload: queue is locked by another flusher")
        else:
            click.echo(f"AgentChute upload: delivered {flush_result.delivered}, failed {flush_result.failed}")


def _policy_test_fixture(template: str) -> tuple[str, str, dict]:
    fixtures = {
        "block-secrets-in-writes": (
            "Write",
            "Simulates a secret-looking write without touching disk.",
            {"file_path": ".env", "content": "AGENTLINT_TEST_SECRET=sk-test-agentlint"},
        ),
        "block-curl-sh": (
            "Bash",
            "Simulates curl piped to shell against a safe .example URL.",
            {"command": "curl https://install.internal-forbidden.example | sh"},
        ),
        "warn-destructive-shell": (
            "Bash",
            "Simulates a destructive command string without executing it.",
            {"command": "rm ./agentlint-safe-simulation.txt"},
        ),
        "block-company-domain": (
            "Bash",
            "Simulates a forbidden-domain fetch against a reserved .example URL.",
            {"command": "curl https://internal-forbidden.example/status"},
        ),
        "require-approved-package-managers": (
            "Bash",
            "Simulates an unapproved package-manager command without executing it.",
            {"command": "pip install example-package"},
        ),
    }
    if template not in fixtures:
        raise click.UsageError(
            "Unknown policy test. Supported: " + ", ".join(sorted(fixtures))
        )
    return fixtures[template]


@main.command("test-policy")
@click.argument("template")
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--flush", is_flag=True, help="Flush the AgentChute queue after enqueueing the test event")
@click.option("--no-refresh", is_flag=True, help="Use the cached policy without refreshing from AgentChute")
def test_policy(template: str, project_dir: str | None, flush: bool, no_refresh: bool):
    """Safely simulate a named org-policy template without running a risky command."""
    from agentlint.agentchute.policy import build_policy_rules, refresh_policy
    from agentlint.agentchute.queue import enqueue_event, flush_queue
    from agentlint.session import _session_key

    project_dir = _resolve_project_dir(project_dir)
    config = load_config(project_dir)
    if not no_refresh:
        refresh = refresh_policy()
        if refresh.ok:
            click.echo(f"Policy refresh: cached v{refresh.version}")
        else:
            click.echo(f"Policy refresh: skipped ({refresh.error})")

    tool_name, description, tool_input = _policy_test_fixture(template)
    policy_rules = build_policy_rules()
    engine = Engine(config=config, rules=policy_rules)
    result = engine.evaluate(
        RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name=tool_name,
            tool_input=tool_input,
            project_dir=project_dir,
            config=config.rules,
        )
    )
    click.echo(f"Safe policy simulation: {description}")
    if result.violations:
        for violation in result.violations:
            click.echo(f"Matched: {violation.rule_id} ({violation.severity.value})")
    else:
        click.echo("Matched: none. Check that the template is installed and policy cache is fresh.")

    event = {
        "v": 1,
        "ts": time.time(),
        "event": "PolicySimulation",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "violations": [{"rule_id": v.rule_id, "severity": v.severity.value} for v in result.violations],
        "rules_evaluated": result.rules_evaluated,
        "is_blocking": result.is_blocking,
        "project_dir": project_dir,
        "agent_platform": "agentlint-test",
        "agentlint_version": __version__,
        "delivery": "queued",
        "policy": _agentchute_policy_metadata(),
    }
    event_id = enqueue_event(event, session_key=_session_key(), config=config)
    if event_id:
        click.echo(f"AgentChute queue: wrote policy simulation {event_id}")
    else:
        click.echo("AgentChute queue: skipped (not enabled or missing key)")
    if flush:
        flush_result = flush_queue(max_events=10)
        if flush_result.aborted_reason:
            click.echo(f"AgentChute upload: skipped ({flush_result.aborted_reason})")
        elif flush_result.locked:
            click.echo("AgentChute upload: queue is locked by another flusher")
        else:
            click.echo(f"AgentChute upload: delivered {flush_result.delivered}, failed {flush_result.failed}")


@main.command("ci-setup")
@click.argument("provider", default="github")
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--dry-run", is_flag=True, help="Print workflow instead of writing it")
def ci_setup(provider: str, project_dir: str | None, dry_run: bool):
    """Generate CI configuration for AgentLint."""
    if provider != "github":
        raise click.UsageError("Only github is supported today.")
    project_dir = _resolve_project_dir(project_dir)
    workflow = """name: AgentLint

on:
  pull_request:
  push:
    branches: [main]

jobs:
  agentlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uvx agentlint ci --format text
"""
    path = Path(project_dir) / ".github" / "workflows" / "agentlint.yml"
    if dry_run:
        click.echo(workflow)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(workflow)
    click.echo(f"Wrote {path}")


@main.group("env")
def env_group():
    """Manage AgentChute shell environment."""


@env_group.command("install")
@click.option("--team-key", prompt=True, hide_input=True, help="AgentChute license key")
@click.option("--api-url", default=None, help="AgentChute API URL")
@click.option("--profile", default=None, help="Shell profile to update")
def env_install(team_key: str, api_url: str | None, profile: str | None):
    """Persist AgentChute env vars into the shell profile."""
    from agentlint.agentchute.client import DEFAULT_API_URL

    path = _persist_agentchute_env(
        api_url=api_url or os.environ.get("AGENTCHUTE_API_URL") or DEFAULT_API_URL,
        team_key=team_key,
        profile=Path(profile).expanduser() if profile else None,
    )
    click.echo(f"Saved AgentChute env vars to {path}")
    click.echo("Open a new terminal or run: source " + str(path))


@env_group.command("show")
def env_show():
    """Show AgentChute env status without revealing secrets."""
    from agentlint.agentchute.client import DEFAULT_API_URL

    key = os.environ.get("AGENTCHUTE_LICENSE_KEY", "")
    masked = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "missing"
    click.echo(f"AGENTCHUTE_API_URL={os.environ.get('AGENTCHUTE_API_URL', DEFAULT_API_URL)}")
    click.echo(f"AGENTCHUTE_LICENSE_KEY={masked}")
    click.echo(f"AGENTCHUTE_ENABLED={os.environ.get('AGENTCHUTE_ENABLED', 'unset')}")
    click.echo(f"Shell profile: {_default_shell_profile()}")


@env_group.command("doctor")
def env_doctor():
    """Check whether AgentChute env vars are available in this shell/profile."""
    profile = _default_shell_profile()
    text = profile.read_text() if profile.exists() else ""
    click.echo(f"Current shell key: {'set' if os.environ.get('AGENTCHUTE_LICENSE_KEY') else 'missing'}")
    click.echo(f"Managed profile block: {'present' if _AGENTCHUTE_ENV_BEGIN in text else 'missing'} ({profile})")


@env_group.command("remove")
@click.option("--profile", default=None, help="Shell profile to update")
def env_remove(profile: str | None):
    """Remove the managed AgentChute env block from the shell profile."""
    path = Path(profile).expanduser() if profile else _default_shell_profile()
    if not path.exists():
        click.echo(f"No profile found at {path}")
        return
    text = path.read_text()
    pattern = re.compile(
        rf"\n?{re.escape(_AGENTCHUTE_ENV_BEGIN)}.*?{re.escape(_AGENTCHUTE_ENV_END)}\n?",
        re.DOTALL,
    )
    path.write_text(pattern.sub("\n", text).strip() + "\n")
    click.echo(f"Removed AgentChute env block from {path}")


@main.command()
@click.option("--dashboard-url", default=None, help="AgentChute dashboard URL")
@click.option("--api-url", default=None, help="AgentChute API URL")
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--manual", is_flag=True, help="Paste a license key instead of using dashboard pairing")
def login(dashboard_url: str | None, api_url: str | None, project_dir: str | None, manual: bool):
    """Pair this machine with AgentChute through the dashboard."""
    from agentlint.agentchute.client import DEFAULT_API_URL

    project_dir = _resolve_project_dir(project_dir)
    api_url = api_url or os.environ.get("AGENTCHUTE_API_URL") or DEFAULT_API_URL
    dashboard_url = dashboard_url or (
        "http://localhost:3001/dashboard/settings/license"
        if "localhost" in api_url
        else "https://app.agentchute.com/dashboard/settings/license"
    )
    team_key: str | None = None
    if not manual:
        try:
            import requests
            import webbrowser

            api_base = api_url.rstrip("/")
            response = requests.post(
                f"{api_base}/dashboard/cli-pairing/start",
                json={"machine_label": f"AgentLint CLI ({Path(project_dir).name})"},
                timeout=(1, 2),
            )
            response.raise_for_status()
            pairing = response.json()
            verification_url = pairing.get("verification_url") or dashboard_url
            click.echo(f"Opening {verification_url}")
            click.echo(f"Pairing code: {pairing.get('user_code')}")
            webbrowser.open(str(verification_url))
            click.echo("Waiting for dashboard approval...")
            deadline = time.time() + 600
            while time.time() < deadline:
                poll = requests.get(
                    f"{api_base}/dashboard/cli-pairing/{pairing['pairing_id']}",
                    timeout=(1, 2),
                )
                poll.raise_for_status()
                status = poll.json()
                if status.get("status") == "approved" and status.get("full_key"):
                    team_key = str(status["full_key"])
                    api_url = str(status.get("api_url") or api_url)
                    break
                if status.get("status") in {"expired", "revoked"}:
                    raise click.ClickException(f"Pairing {status['status']}")
                time.sleep(2)
            if team_key is None:
                raise click.ClickException("Pairing timed out")
        except Exception as exc:
            click.echo(f"Dashboard pairing unavailable ({exc}). Falling back to manual key paste.")

    if team_key is None:
        import webbrowser
        click.echo(f"Opening {dashboard_url}")
        webbrowser.open(dashboard_url)
        team_key = click.prompt("Paste the AgentChute license key", hide_input=True)

    profile = _persist_agentchute_env(api_url=api_url, team_key=team_key)
    config_path = Path(project_dir) / "agentlint.yml"
    if config_path.exists():
        _ensure_agentchute_enabled_config(config_path)
    click.echo(f"Paired. Env vars saved to {profile}")


@main.group("queue")
def queue_group():
    """Inspect and flush the local AgentChute queue."""


@queue_group.command("status")
def queue_status_command():
    """Show local AgentChute queue status."""
    from agentlint.agentchute.queue import queue_status

    status_data = queue_status()
    click.echo(f"Queue: {status_data['queue_path']}")
    click.echo(f"Pending: {status_data['pending']}")
    click.echo(f"Queued total: {status_data['queued']}")
    click.echo(f"Delivered cursor: {status_data['delivered_cursor']}")
    click.echo(f"Failures: {status_data['failures']}")


@queue_group.command("flush")
@click.option("--max-events", default=None, type=int, help="Maximum events to flush")
def queue_flush_command(max_events: int | None):
    """Flush queued AgentChute events now."""
    _flush_agentchute_queue(max_events=max_events, dry_run=False, background=False)


@queue_group.command("inspect")
@click.option("--last", "last_n", default=5, type=int, help="Show the last N queued events")
def queue_inspect(last_n: int):
    """Show privacy-safe queued event summaries."""
    from agentlint.agentchute.queue import _queue_path, _read_lines

    lines = _read_lines()
    if not lines:
        click.echo("Queue is empty.")
        return
    for raw in lines[-last_n:]:
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            click.echo("poison line: invalid JSON")
            continue
        event = item.get("event") or {}
        click.echo(
            f"{item.get('line_offset', '?')}: {event.get('event', '?')} "
            f"{event.get('tool_name', '')} session={item.get('session_key', '')} "
            f"violations={len(event.get('violations') or [])}"
        )
    click.echo(f"Queue file: {_queue_path()}")


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
    installed = load_installed_rules()
    if pack is not None:
        installed = [r for r in installed if r.pack == pack]
    rules.extend(installed)
    if config.custom_rules_dir:
        custom = load_custom_rules(config.custom_rules_dir, project_dir)
        if pack is not None:
            custom = [r for r in custom if r.pack == pack]
        rules.extend(custom)
    if pack is None or pack == "universal":
        from agentlint.agentchute.policy import build_policy_rules
        rules.extend(build_policy_rules())

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
    """Show AgentLint health for the current project."""
    from importlib.metadata import version as get_version
    from agentlint.agentchute.client import (
        DEFAULT_API_URL,
        ENV_AGENTCHUTE_API_URL,
        ENV_AGENTCHUTE_ENABLED,
        ENV_AGENTCHUTE_LICENSE_KEY,
    )
    from agentlint.agentchute.policy import policy_status
    from agentlint.agentchute.queue import queue_status

    project_dir = _resolve_project_dir(project_dir)
    try:
        ver = get_version("agentlint")
    except Exception:
        ver = "dev"
    install_kind, update_cmd = _detect_update_command()
    config_path = Path(project_dir) / "agentlint.yml"
    config_ok = config_path.exists()

    click.echo(f"AgentLint v{ver}")
    click.echo(f"Install: {install_kind} ({' '.join(update_cmd)})")
    click.echo(f"Project config: {'ok' if config_ok else 'missing'}")

    detected = _detected_agent_platforms(project_dir)
    click.echo("Coding agents:")
    for platform in _HOOK_PLATFORMS:
        state, path = _hook_status(platform, project_dir)
        marker = "✓" if state == "installed" else "!" if state == "stale" else "○"
        suffix = f" ({path})" if state in {"installed", "stale", "custom"} else ""
        detected_note = " detected" if platform in detected else ""
        click.echo(f"  {marker} {platform:<8} {state}{detected_note}{suffix}")

    env_enabled = os.environ.get(ENV_AGENTCHUTE_ENABLED, "")
    key = os.environ.get(ENV_AGENTCHUTE_LICENSE_KEY, "")
    api_url = os.environ.get(ENV_AGENTCHUTE_API_URL, DEFAULT_API_URL)
    queue = queue_status()
    policy = policy_status()

    click.echo("AgentChute:")
    click.echo(f"  Enabled: {env_enabled or 'config/default'}")
    click.echo(f"  API: {api_url}")
    click.echo(f"  Key: {'set' if key else 'missing'}")
    click.echo(f"  Events queued: {queue['pending']} pending / {queue['queued']} total")
    if queue.get("next_attempt_at"):
        click.echo(f"  Retry scheduled: {queue['next_attempt_at']}")
    policy_line = "none"
    if policy.get("cached"):
        policy_line = f"v{policy.get('version')} updated {policy.get('updated_at') or 'unknown'}"
    if policy.get("error"):
        policy_line += f" (error: {policy['error']})"
    click.echo(f"  Cloud policy: {policy_line}")

    config = load_config(project_dir)
    rules = load_project_rules(config, project_dir)
    click.echo(f"Rules: {len(rules)} active | Severity: {config.severity} | Packs: {', '.join(config.packs)}")
    if config.projects:
        click.echo("Projects:")
        for prefix, proj in sorted(config.projects.items()):
            proj_packs = ", ".join(proj.get("packs", []))
            click.echo(f"  {prefix} → {proj_packs}")

    click.echo("")
    click.echo("Next: agentlint doctor --fix" if not config_ok or any(_hook_status(p, project_dir)[0] in {"missing", "stale"} for p in detected) else "All primary checks look healthy.")


@main.command()
@click.option("--project-dir", default=None, help="Project directory")
@click.option("--fix", is_flag=True, help="Repair common issues automatically")
def doctor(project_dir: str | None, fix: bool):
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
        if fix:
            ctx = click.Context(init)
            ctx.invoke(init, project_dir=project_dir, team_key=None)
            checks_ok.append("Fix: created agentlint.yml")

    config = load_config(project_dir)
    detected_platforms = _detected_agent_platforms(project_dir)
    for platform in detected_platforms:
        hook_state, hook_path = _hook_status(platform, project_dir)
        if hook_state == "installed":
            checks_ok.append(f"Hooks: {platform} installed ({hook_path})")
        elif hook_state == "stale":
            issues.append(f"Hooks: {platform} points to an old AgentLint binary ({hook_path})")
            if fix:
                get_adapter(platform).install_hooks(project_dir, scope="project", cmd=resolve_command())
                checks_ok.append(f"Fix: reinstalled {platform} hooks")
        elif hook_state == "missing":
            issues.append(f"Hooks: {platform} not installed")
            if fix:
                get_adapter(platform).install_hooks(project_dir, scope="project", cmd=resolve_command())
                checks_ok.append(f"Fix: installed {platform} hooks")
        elif hook_state == "custom":
            checks_ok.append(f"Hooks: {platform} config exists without AgentLint")
    installed_detected = [p for p in detected_platforms if _hook_status(p, project_dir)[0] == "installed"]
    if "claude" in installed_detected and "cursor" in installed_detected:
        checks_ok.append("Hooks: installed for both Claude and Cursor")

    if fix and "codex" in detected_platforms:
        _enable_codex_hooks()
        checks_ok.append("Fix: Codex hooks feature enabled under [features]")

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

    from agentlint.agentchute.client import ENV_AGENTCHUTE_LICENSE_KEY
    from agentlint.agentchute.policy import refresh_policy
    from agentlint.agentchute.queue import _queue_root
    queue_root = _queue_root()
    try:
        queue_root.mkdir(parents=True, exist_ok=True)
        checks_ok.append(f"AgentChute queue: {queue_root} (writable)")
    except OSError:
        issues.append(f"AgentChute queue: {queue_root} is not writable")

    agentchute_cfg = getattr(config, "agentchute", None)
    agentchute_configured = bool(
        os.environ.get(ENV_AGENTCHUTE_LICENSE_KEY)
        or (isinstance(agentchute_cfg, dict) and agentchute_cfg.get("enabled"))
    )
    if os.environ.get(ENV_AGENTCHUTE_LICENSE_KEY):
        policy_result = refresh_policy()
        if policy_result.ok:
            checks_ok.append(f"Cloud policy: refreshed v{policy_result.version}")
        else:
            issues.append(f"Cloud policy: {policy_result.error}")
    elif agentchute_configured:
        issues.append("AgentChute env: AGENTCHUTE_LICENSE_KEY not set")

    # Check custom rules
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

    if platform not in _SUPPORTED_ADAPTERS:
        raise click.UsageError(
            f"Unknown platform: {platform}. Supported: {', '.join(_SUPPORTED_ADAPTERS)}"
        )
    adapter = get_adapter(platform)

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


@main.group()
def agentchute():
    """Manage AgentChute queue, policy, and cloud status."""


@agentchute.command("status")
def agentchute_status():
    """Show local AgentChute queue and policy status."""
    from agentlint.agentchute.policy import policy_status
    from agentlint.agentchute.queue import queue_status

    q = queue_status()
    p = policy_status()
    click.echo("AgentChute")
    click.echo(f"  Queue: {q['pending']} pending / {q['queued']} total")
    click.echo(f"  Queue path: {q['queue_path']}")
    if q.get("next_attempt_at"):
        click.echo(f"  Next upload attempt: {q['next_attempt_at']}")
    click.echo(f"  Policy: {'cached' if p['cached'] else 'not cached'}")
    if p.get("version") is not None:
        click.echo(f"  Policy version: {p['version']}")
    if p.get("updated_at"):
        click.echo(f"  Policy updated: {p['updated_at']}")
    if p.get("error"):
        click.echo(f"  Policy error: {p['error']}")


@agentchute.command("flush")
@click.option("--background", is_flag=True, help="Bounded background flush mode")
@click.option("--max-events", default=None, type=int, help="Maximum queued events to send")
@click.option("--batch-size", default=50, type=int, help="Maximum events per API batch")
@click.option("--time-budget", default=3.0, type=float, help="Maximum seconds to spend flushing")
@click.option("--dry-run", is_flag=True, help="Count events without POSTing")
def agentchute_flush(
    background: bool,
    max_events: int | None,
    batch_size: int,
    time_budget: float,
    dry_run: bool,
):
    """Flush queued AgentChute events now."""
    _flush_agentchute_queue(
        background=background,
        max_events=max_events,
        batch_size=batch_size,
        time_budget=time_budget,
        dry_run=dry_run,
    )


@main.command("sync")
@click.option("--background", is_flag=True, help="Bounded background flush mode")
@click.option("--max-events", default=None, type=int, help="Maximum queued events to send")
@click.option("--batch-size", default=50, type=int, help="Maximum events per API batch")
@click.option("--time-budget", default=3.0, type=float, help="Maximum seconds to spend flushing")
@click.option("--dry-run", is_flag=True, help="Count events without POSTing")
def sync(
    background: bool,
    max_events: int | None,
    batch_size: int,
    time_budget: float,
    dry_run: bool,
):
    """Sync queued AgentChute events now."""
    _flush_agentchute_queue(
        background=background,
        max_events=max_events,
        batch_size=batch_size,
        time_budget=time_budget,
        dry_run=dry_run,
    )


def _flush_agentchute_queue(
    *,
    background: bool,
    max_events: int | None,
    batch_size: int,
    time_budget: float,
    dry_run: bool,
) -> None:
    from agentlint.agentchute.queue import flush_queue

    result = flush_queue(
        max_events=max_events,
        batch_size=batch_size,
        time_budget_s=time_budget,
        dry_run=dry_run,
    )
    if background:
        return
    if result.locked:
        click.echo("Another AgentChute flusher is already running.")
        return
    if result.aborted_reason:
        click.echo(f"Flush aborted: {result.aborted_reason}", err=True)
        raise click.exceptions.Exit(2)
    verb = "Would deliver" if dry_run else "Delivered"
    click.echo(
        f"{verb} {result.delivered} event(s). "
        f"({result.failed} failed, {result.skipped} skipped, {result.attempted} attempted)"
    )


@agentchute.command("refresh")
def agentchute_refresh():
    """Refresh cached AgentChute org policy."""
    from agentlint.agentchute.policy import refresh_policy

    result = refresh_policy()
    if not result.ok:
        click.echo(f"Policy refresh failed: {result.error}", err=True)
        raise click.exceptions.Exit(2)
    click.echo(f"Policy cached: version {result.version}")


@agentchute.command("policy")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]))
def agentchute_policy(output_format: str):
    """Show cached AgentChute org policy."""
    from agentlint.agentchute.policy import load_cached_policy

    policy = load_cached_policy()
    if policy is None:
        click.echo("No AgentChute policy cache found.")
        raise click.exceptions.Exit(1)
    if output_format == "json":
        click.echo(json.dumps(policy, indent=2, sort_keys=True))
        return
    click.echo(f"Policy version: {policy.get('version', 'unknown')}")
    click.echo(f"Rules: {len(policy.get('rules') or [])} declarative")
    click.echo(f"Required packs: {len(policy.get('required_packs') or [])}")


@main.group("policy")
def policy_group():
    """Inspect and refresh cached AgentChute workspace policy."""


@policy_group.command("status")
def policy_status_command():
    """Show local policy cache status."""
    from agentlint.agentchute.policy import policy_status

    status_data = policy_status()
    click.echo(f"Workspace policy: {'cached' if status_data['cached'] else 'not cached'}")
    if status_data.get("version") is not None:
        click.echo(f"Version: {status_data['version']}")
    if status_data.get("updated_at"):
        click.echo(f"Updated: {status_data['updated_at']}")
    if status_data.get("error"):
        click.echo(f"Error: {status_data['error']}")


@policy_group.command("refresh")
def policy_refresh_command():
    """Refresh cached AgentChute workspace policy."""
    from agentlint.agentchute.policy import refresh_policy

    result = refresh_policy()
    if not result.ok:
        click.echo(f"Policy refresh failed: {result.error}", err=True)
        raise click.exceptions.Exit(2)
    click.echo(f"Policy cached: version {result.version}")


@policy_group.command("explain")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]))
def policy_explain_command(output_format: str):
    """Explain effective cached policy behavior."""
    from agentlint.agentchute.policy import (
        load_cached_policy,
        missing_required_packs,
        policy_status,
        required_packs,
    )

    policy = load_cached_policy()
    status_data = policy_status()
    if policy is None:
        click.echo("No AgentChute policy cache found.")
        if status_data.get("error"):
            click.echo(f"Policy error: {status_data['error']}")
        raise click.exceptions.Exit(1)

    rules = [rule for rule in policy.get("rules") or [] if isinstance(rule, dict)]
    active_rules = [rule for rule in rules if rule.get("enabled", True) is not False]
    locked_rules = [rule for rule in active_rules if rule.get("locked") is True]
    packs = required_packs(policy)
    missing = missing_required_packs(policy)
    cloud_feeds = [
        str(pack.get("id") or pack.get("name"))
        for pack in packs
        if pack.get("type") == "cloud_feed" or pack.get("managed_by") == "agentchute"
    ]
    if output_format == "json":
        click.echo(json.dumps({
            "cached": True,
            "version": policy.get("version"),
            "updated_at": policy.get("updated_at"),
            "organization_id": policy.get("organization_id"),
            "rules": len(active_rules),
            "locked_rules": len(locked_rules),
            "required_packs": len(packs),
            "cloud_feeds": cloud_feeds,
            "missing_required_packs": missing,
            "hook_behavior": "local-only, no network required",
        }, indent=2, sort_keys=True))
        return

    click.echo(f"Workspace policy: v{policy.get('version', 'unknown')}")
    click.echo("Source: AgentChute")
    click.echo(f"Cache: {'valid' if status_data['cached'] else 'missing'}")
    if policy.get("updated_at"):
        click.echo(f"Updated: {policy['updated_at']}")
    click.echo(f"Rules: {len(active_rules)} active, {len(locked_rules)} locked")
    click.echo(f"Required packs: {len(packs)}")
    if cloud_feeds:
        click.echo(f"Cloud feeds: {', '.join(cloud_feeds)}")
    if missing:
        click.echo(f"Missing custom packs: {', '.join(missing)}")
    click.echo("Hook behavior: local-only, no network required")


if __name__ == "__main__":
    main()
