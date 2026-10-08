"""Hook coverage: is AgentLint configured, enabled and actually observed per agent?

`status` and `doctor` previously only looked at project-local hook files, so
user-scope installations (e.g. ``~/.codex/hooks.json``) were reported as
missing. This module checks both scopes using each adapter's own path logic,
parses hook files for the events that reach AgentLint, and reads a small
heartbeat written by ``agentlint check`` to prove hooks are really invoked.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path

HOOK_PLATFORMS = ("claude", "cursor", "codex", "gemini", "continue", "kimi", "grok")
STALE_HEARTBEAT_SECONDS = 24 * 3600

# Adapter module and path function for each platform; both accept (scope, project_dir).
_PATH_FUNCS = {
    "claude": ("agentlint.adapters.claude", "_settings_path"),
    "cursor": ("agentlint.adapters.cursor", "_hooks_path"),
    "codex": ("agentlint.adapters.codex", "_hooks_path"),
    "gemini": ("agentlint.adapters.gemini", "_settings_path"),
    "continue": ("agentlint.adapters.continue_dev", "_settings_path"),
    "kimi": ("agentlint.adapters.kimi", "_config_path"),
    "grok": ("agentlint.adapters.grok", "_settings_path"),
}

_CHECK_RE = re.compile(r"agentlint[\"']?\s+check\b|-m\s+agentlint\s+check\b", re.IGNORECASE)
_STALE_BINARY_RE = re.compile(r"/[^\s\"']*agentlint(?:\s|$)")


@dataclass
class HookInstall:
    scope: str
    path: str
    state: str  # installed | wrapper | stale | custom | unreadable | missing
    events: list[str] = field(default_factory=list)


@dataclass
class PlatformCoverage:
    platform: str
    installs: list[HookInstall]
    enabled: bool | None  # None = cannot be determined locally
    heartbeat: dict | None

    @property
    def configured(self) -> HookInstall | None:
        """The active installation (project scope wins over user scope)."""
        for install in self.installs:
            if install.state in {"installed", "wrapper", "stale"}:
                return install
        return None

    @property
    def state(self) -> str:
        active = self.configured
        if active:
            return active.state
        if any(i.state == "custom" for i in self.installs):
            return "custom"
        if any(i.state == "unreadable" for i in self.installs):
            return "unreadable"
        return "missing"

    def observed_age(self, now: float | None = None) -> float | None:
        if not self.heartbeat or not isinstance(self.heartbeat.get("ts"), (int, float)):
            return None
        return max(0.0, (now or time.time()) - self.heartbeat["ts"])

    def to_dict(self) -> dict:
        active = self.configured
        return {
            "platform": self.platform,
            "state": self.state,
            "scope": active.scope if active else None,
            "path": active.path if active else None,
            "events": active.events if active else [],
            "enabled": self.enabled,
            "installs": [i.__dict__ for i in self.installs],
            "last_seen": self.heartbeat,
            "last_seen_age_seconds": self.observed_age(),
        }


def hook_path(platform: str, scope: str, project_dir: str) -> Path | None:
    entry = _PATH_FUNCS.get(platform)
    if entry is None:
        return None
    module, func = entry
    return getattr(import_module(module), func)(scope, project_dir)


def _wired_events(data: object) -> list[str]:
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return []
    return sorted(
        event
        for event, entries in hooks.items()
        if "agentlint" in json.dumps(entries, default=str).lower()
    )


def inspect_hook_file(path: Path, resolved_command: str | None = None) -> HookInstall:
    """Classify one hook file without executing anything it references."""
    if not path.exists():
        return HookInstall(scope="", path=str(path), state="missing")
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return HookInstall(scope="", path=str(path), state="unreadable")
    if "agentlint" not in text.lower():
        return HookInstall(scope="", path=str(path), state="custom")
    try:
        events = _wired_events(json.loads(text))
    except json.JSONDecodeError:
        events = []
    if not _CHECK_RE.search(text):
        # A command references AgentLint (e.g. a scoped wrapper script) but does
        # not call `agentlint check` directly; it delegates, so it is not missing.
        return HookInstall(scope="", path=str(path), state="wrapper", events=events)
    if resolved_command and resolved_command not in text and _STALE_BINARY_RE.search(text):
        return HookInstall(scope="", path=str(path), state="stale", events=events)
    return HookInstall(scope="", path=str(path), state="installed", events=events)


def _heartbeat_dir() -> Path:
    return Path(
        os.environ.get("AGENTLINT_HEARTBEAT_DIR", "~/.cache/agentlint/heartbeat")
    ).expanduser()


def project_fingerprint(project_dir: str) -> str:
    return hashlib.sha256(os.path.realpath(project_dir).encode()).hexdigest()[:16]


def record_heartbeat(platform: str, *, event: str, tool: str, project_dir: str, version: str):
    """Record that a hook invocation reached AgentLint. Never stores content."""
    directory = _heartbeat_dir()
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "platform": platform,
        "event": event,
        "tool": tool if re.fullmatch(r"[A-Za-z0-9_.:-]{0,64}", tool or "") else "[other]",
        "project": project_fingerprint(project_dir),
        "version": version,
        "ts": time.time(),
    }
    target = directory / f"{platform}.json"
    tmp = target.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload))
    os.replace(tmp, target)


def read_heartbeat(platform: str) -> dict | None:
    try:
        data = json.loads((_heartbeat_dir() / f"{platform}.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def platform_coverage(
    platform: str,
    project_dir: str,
    *,
    resolved_command: str | None = None,
    codex_enabled: bool | None = None,
) -> PlatformCoverage:
    installs: list[HookInstall] = []
    for scope in ("project", "user"):
        path = hook_path(platform, scope, project_dir)
        if path is None:
            continue
        install = inspect_hook_file(path, resolved_command)
        install.scope = scope
        installs.append(install)
    return PlatformCoverage(
        platform=platform,
        installs=installs,
        enabled=codex_enabled if platform == "codex" else None,
        heartbeat=read_heartbeat(platform),
    )


def format_age(seconds: float | None) -> str:
    if seconds is None:
        return "never observed"
    if seconds < 90:
        return f"{int(seconds)}s ago"
    if seconds < 5400:
        return f"{int(seconds // 60)}m ago"
    if seconds < 172800:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def describe(coverage: PlatformCoverage, project_dir: str) -> str:
    """One-line, three-tier summary: configured -> enabled -> observed."""
    active = coverage.configured
    if active:
        events = f" [{', '.join(active.events)}]" if active.events else ""
        configured = f"{active.state} ({active.scope}: {active.path}){events}"
    else:
        configured = coverage.state
    parts = [f"configured: {configured}"]
    if coverage.enabled is not None:
        parts.append(f"enabled: {'yes' if coverage.enabled else 'NO'}")
    age = coverage.observed_age()
    observed = format_age(age)
    if coverage.heartbeat:
        here = coverage.heartbeat.get("project") == project_fingerprint(project_dir)
        observed += (
            f" ({coverage.heartbeat.get('event')}, {'this project' if here else 'another project'})"
        )
        if age is not None and age > STALE_HEARTBEAT_SECONDS:
            observed += " — stale"
    parts.append(f"observed: {observed}")
    return " | ".join(parts)
