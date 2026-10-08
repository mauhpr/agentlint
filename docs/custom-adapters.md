# Writing a custom adapter

An adapter connects one coding agent to AgentLint. This page is for contributors
adding support for a new agent to the AgentLint package. If you only want to run
AgentLint from your own tool without changing AgentLint, the
[generic adapter](agents/generic.md) or the [MCP server](mcp.md) is usually
enough.

AgentLint 2.9.0 ships 10 adapters: `claude`, `cursor`, `codex`, `gemini`,
`continue`, `kimi`, `grok`, `openai`, `mcp` and `generic`. They live in
`src/agentlint/adapters/`. Read one of the hook-based ones (`gemini.py` is
short) before starting.

## What an adapter does

An adapter is a subclass of `AgentAdapter` (`src/agentlint/adapters/base.py`).
It is responsible for:

1. Translating the agent's native event names to `AgentEvent`.
2. Mapping the agent's tool names to `NormalizedTool`.
3. Resolving the project directory and a session key.
4. Supplying the output formatter whose JSON and exit code the agent understands.
5. Installing and removing AgentLint's hook entries in the agent's config file.

All abstract members:

| Member | Signature | Used by |
|--------|-----------|---------|
| `platform_name` | property, `-> str` | `check` (sets `RuleContext.agent_platform`, coverage heartbeat, diagnostic bundle) |
| `formatter` | property, `-> OutputFormatter` | `check` (output text and exit code) |
| `resolve_project_dir()` | `-> str` | MCP and OpenAI adapters, programmatic use |
| `resolve_session_key()` | `-> str` | MCP server, programmatic use |
| `translate_event(native_event)` | `-> AgentEvent`, raise `ValueError` if unknown | `check --event` |
| `normalize_tool_name(native_tool)` | `-> str` (a `NormalizedTool` value) | `check` (translates native tool calls before rules run) |
| `build_rule_context(event, raw_payload, project_dir, session_state)` | `-> RuleContext` | MCP/OpenAI adapters, programmatic use |
| `install_hooks(project_dir, scope="project", dry_run=False, cmd=None)` | `-> None` | `agentlint setup <name>` |
| `uninstall_hooks(project_dir, scope="project")` | `-> None` | `agentlint uninstall <name>` |

### How `agentlint check` uses an adapter

Hook-based agents run `agentlint check --adapter <name> --event <NativeEvent>`
and send JSON on stdin. In 2.9.0 the `check` command:

- calls `translate_event()` on the `--event` value. If that raises `ValueError`,
  it falls back to `AgentEvent.from_string()`, so generic values such as
  `pre_tool_use` also work;
- builds the `RuleContext` itself from the payload keys `tool_name`,
  `tool_input`, `prompt`, `last_assistant_message` (or `subagent_output`),
  `notification_type`, `compact_source`, `agent_transcript_path`, `agent_type`,
  `agent_id` and `tool_response`. It does not call `build_rule_context()`;
- uses `platform_name` for `agent_platform`, the coverage heartbeat and the
  diagnostic bundle;
- passes the violations to `formatter.format()` and exits with
  `formatter.exit_code()`.

Session state comes from `agentlint.session`, which reads
`AGENTLINT_SESSION_ID`, `CLAUDE_SESSION_ID`, `CURSOR_SESSION_ID` or
`OPENAI_SESSION_ID` and falls back to the parent PID. Your agent can set
`AGENTLINT_SESSION_ID` in the hook environment.

**Tool names matter.** Built-in rules check the canonical tool names `Bash`,
`Write` and `Edit` and the input keys `command`, `file_path`, `content`,
`old_string` and `new_string`. Before evaluating, `check` translates native
tool calls through your adapter's `normalize_tool_name()`: tools that map to
`shell`, `file_write` or `file_edit` become `Bash`, `Write` and `Edit`, and
common native input keys (`path`, `cmd`, `old_str`, ...) are copied to the
canonical ones (`agentlint/adapters/normalize.py`). So map every shell and file
tool your agent has, and check real payloads with
`agentlint check --diagnostic-bundle` (see [diagnostics.md](diagnostics.md)).

## Example adapter

This adapter supports a hypothetical agent called Acme. Acme reads hooks from
`.acme/hooks.json` (project) or `~/.acme/hooks.json` (user), sends
`beforeTool` / `afterTool` / `sessionEnd` events, and accepts the same JSON
shape as `PlainJsonFormatter`.

```python
# src/agentlint/adapters/acme.py
"""Acme agent adapter for AgentLint."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import click

from agentlint.adapters._utils import (
    is_agentlint_nested_entry,
    read_json_config,
    resolve_command,
    write_json_config,
)
from agentlint.adapters.base import AgentAdapter
from agentlint.formats.plain_json import PlainJsonFormatter
from agentlint.models import AgentEvent, NormalizedTool, RuleContext, to_hook_event

_ACME_EVENT_MAP: dict[str, AgentEvent] = {
    "beforeTool": AgentEvent.PRE_TOOL_USE,
    "afterTool": AgentEvent.POST_TOOL_USE,
    "sessionEnd": AgentEvent.STOP,
}

_ACME_TOOL_MAP: dict[str, NormalizedTool] = {
    "Bash": NormalizedTool.SHELL,
    "Write": NormalizedTool.FILE_WRITE,
    "Edit": NormalizedTool.FILE_EDIT,
    "Read": NormalizedTool.FILE_READ,
}


def _hooks_path(scope: str, project_dir: str | None = None) -> Path:
    """Return the Acme hook file. Signature must be (scope, project_dir)."""
    if scope == "user":
        return Path.home() / ".acme" / "hooks.json"
    base = Path(project_dir) if project_dir else Path.cwd()
    return base / ".acme" / "hooks.json"


def _build_hooks(cmd: str) -> dict[str, list[dict]]:
    """Hook entries keyed by native event name."""
    hooks: dict[str, list[dict]] = {}
    for event, timeout in (("beforeTool", 5), ("afterTool", 10), ("sessionEnd", 30)):
        hooks[event] = [
            {
                "matcher": "Bash|Write|Edit",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{cmd} check --event {event} --adapter acme",
                        "timeout": timeout,
                    }
                ],
            }
        ]
    return hooks


class AcmeAdapter(AgentAdapter):
    """AgentAdapter implementation for the Acme agent."""

    @property
    def platform_name(self) -> str:
        return "acme"

    @property
    def formatter(self) -> PlainJsonFormatter:
        return PlainJsonFormatter()

    def resolve_project_dir(self) -> str:
        return (
            os.environ.get("AGENTLINT_PROJECT_DIR")
            or os.environ.get("ACME_PROJECT_DIR")
            or os.getcwd()
        )

    def resolve_session_key(self) -> str:
        return (
            os.environ.get("AGENTLINT_SESSION_ID")
            or os.environ.get("ACME_SESSION_ID")
            or f"pid-{os.getppid()}"
        )

    def translate_event(self, native_event: str) -> AgentEvent:
        try:
            return _ACME_EVENT_MAP[native_event]
        except KeyError as exc:
            raise ValueError(f"Unknown Acme event: {native_event}") from exc

    def normalize_tool_name(self, native_tool: str) -> str:
        return _ACME_TOOL_MAP.get(native_tool, NormalizedTool.UNKNOWN).value

    def build_rule_context(
        self,
        event: AgentEvent,
        raw_payload: dict[str, Any],
        project_dir: str,
        session_state: dict,
    ) -> RuleContext:
        return RuleContext(
            event=to_hook_event(event),
            tool_name=raw_payload.get("tool_name", ""),
            tool_input=raw_payload.get("tool_input", {}),
            project_dir=project_dir,
            config={},
            session_state=session_state,
            prompt=raw_payload.get("prompt"),
            agent_platform="acme",
        )

    def install_hooks(
        self,
        project_dir: str,
        scope: str = "project",
        dry_run: bool = False,
        cmd: str | None = None,
    ) -> None:
        cmd = cmd or resolve_command()
        path = _hooks_path(scope, project_dir)
        existing = read_json_config(path)
        if existing is None:
            raise click.ClickException(f"{path} is not valid JSON; fix it and retry.")

        settings = dict(existing)
        hooks = dict(settings.get("hooks", {}))
        for event, ours in _build_hooks(cmd).items():
            # Drop our previous entries so repeated installs are idempotent.
            kept = [e for e in hooks.get(event, []) if not is_agentlint_nested_entry(e)]
            hooks[event] = kept + ours
        settings["hooks"] = hooks

        if dry_run:
            click.echo(f"\nDry run - would write to {path}:")
            click.echo(json.dumps(settings, indent=2))
            return
        write_json_config(path, settings)

    def uninstall_hooks(self, project_dir: str, scope: str = "project") -> None:
        path = _hooks_path(scope, project_dir)
        existing = read_json_config(path)
        if not existing:
            return  # Missing (empty dict) or corrupted (None): leave it alone.

        settings = dict(existing)
        hooks = {
            event: [e for e in entries if not is_agentlint_nested_entry(e)]
            for event, entries in settings.get("hooks", {}).items()
        }
        hooks = {event: entries for event, entries in hooks.items() if entries}
        if hooks:
            settings["hooks"] = hooks
        else:
            settings.pop("hooks", None)
        write_json_config(path, settings)
```

Helpers in `agentlint.adapters._utils`:

- `resolve_command()` returns the absolute command used to run `agentlint`.
- `read_json_config(path)` returns `{}` for a missing file and `None` for a
  corrupted one.
- `write_json_config(path, data)` creates parent directories and writes
  indented JSON.
- `is_agentlint_nested_entry(entry)` / `is_agentlint_flat_entry(entry)` detect
  entries AgentLint installed earlier, for
  `{"matcher": ..., "hooks": [{"command": ...}]}` and `{"command": ...}` shapes.

If the agent needs a different response format, add a formatter in
`src/agentlint/formats/` that subclasses `OutputFormatter`
(`src/agentlint/formats/base.py`) and implements `format()` and `exit_code()`.
Both receive either an `AgentEvent` or the raw `--event` string, so handle both.

```python
# src/agentlint/formats/acme_hooks.py
"""Acme hook response formatter."""

from __future__ import annotations

import json

from agentlint.formats.base import OutputFormatter
from agentlint.models import AgentEvent, Severity, Violation


class AcmeHookFormatter(OutputFormatter):
    """Deny on ERROR, otherwise return advisory text."""

    def exit_code(self, violations: list[Violation], event: AgentEvent | str = "") -> int:
        return 2 if any(v.severity == Severity.ERROR for v in violations) else 0

    def format(self, violations: list[Violation], event: AgentEvent | str = "") -> str | None:
        if not violations:
            return None
        blocked = any(v.severity == Severity.ERROR for v in violations)
        return json.dumps(
            {
                "decision": "deny" if blocked else "allow",
                "message": "\n".join(self._format_violation_lines(violations)),
            }
        )
```

## Registering the adapter

There is no plugin mechanism for adapters; they are registered in several
places in the package. Do all of these.

### 1. Adapter registry

`src/agentlint/adapters/__init__.py`: add the dotted path to
`_ADAPTER_REGISTRY` and the name to the `get_adapter()` docstring.
`agentlint setup` and `agentlint uninstall` use `get_adapter()`.

```python
_ADAPTER_REGISTRY: dict[str, str] = {
    # ... existing entries ...
    "acme": "agentlint.adapters.acme.AcmeAdapter",
}
```

### 2. Supported platform names

`src/agentlint/cli.py`: add the name to `_SUPPORTED_ADAPTERS`. `setup` and
`uninstall` reject names that are not in this tuple.

```python
_SUPPORTED_ADAPTERS = (
    # ... existing names ...
    "acme",
)
```

### 3. `check --adapter` mapping

`src/agentlint/cli.py`: import the class at the top of the module and add it to
the `_ADAPTERS` dict inside `_resolve_adapter()`. If the agent sets a
recognisable environment variable, add an auto-detection branch before the
Claude default.

```python
from agentlint.adapters.acme import AcmeAdapter

# inside _resolve_adapter():
    _ADAPTERS: dict[str, Any] = {
        # ... existing entries ...
        "acme": AcmeAdapter,
    }
    # ...
    if os.environ.get("ACME_SESSION_ID") or os.environ.get("ACME_PROJECT_DIR"):
        return AcmeAdapter()
```

Installed hooks should always pass `--adapter <name>` explicitly; auto-detection
is a fallback.

### 4. Hook platform lists (hook-based adapters only)

Skip this step for adapters that are not driven by a hook file (like `openai`,
`mcp` and `generic`).

In `src/agentlint/cli.py`:

- add the name to `_HOOK_PLATFORMS` (used by `onboard`, `setup-agent`,
  `status` and `doctor`);
- add the project hook file to `_platform_hook_file()`;
- add the agent's environment markers to `env_markers` in
  `_detected_agent_platforms()`.

In `src/agentlint/coverage.py`:

- add the name to `HOOK_PLATFORMS` (keep it identical to `cli._HOOK_PLATFORMS`);
- add `(module, function)` to `_PATH_FUNCS`. The function must accept
  `(scope, project_dir)` and return a `Path`; coverage calls it for both
  `"project"` and `"user"` scope.

```python
# src/agentlint/coverage.py
_PATH_FUNCS = {
    # ... existing entries ...
    "acme": ("agentlint.adapters.acme", "_hooks_path"),
}
```

Coverage reads the hook file without executing it. It reports the events that
mention AgentLint under a top-level `"hooks"` object in a JSON file, and
classifies the install as installed, wrapper, stale, custom or missing. The
heartbeat (`record_heartbeat()`, called by `check`) proves the hook really ran,
keyed by `platform_name`.

### 5. Tool-name map

`src/agentlint/core/models.py`: if the agent's tool names differ from Claude
Code's, add a map to `_PLATFORM_TOOL_MAPS` so `RuleContext.normalized_tool`
works for `agent_platform == "acme"`. Without an entry it falls back to the
Claude map.

### 6. Tests

Add `tests/test_acme_adapter.py`, following `tests/test_gemini_adapter.py` or
`tests/test_cursor_adapter.py`. Cover at least:

- every native event in `translate_event()`, and that an unknown event raises
  `ValueError`;
- `normalize_tool_name()` for each mapped tool and an unknown one;
- `build_rule_context()` fields;
- `_hooks_path()` for project and user scope (monkeypatch `Path.home`);
- install into an empty directory, repeated install (idempotent), preserving
  third-party hooks, `dry_run` writing nothing;
- uninstall removing only AgentLint entries, and leaving a corrupted file alone;
- the formatter's output and exit code for ERROR, WARNING and no violations;
- an end-to-end `check` run through `click.testing.CliRunner` with
  `--adapter acme` and a real payload.

```python
# tests/test_acme_adapter.py
from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from agentlint.adapters.acme import AcmeAdapter, _hooks_path
from agentlint.cli import main
from agentlint.models import AgentEvent, NormalizedTool


def test_translates_before_tool() -> None:
    assert AcmeAdapter().translate_event("beforeTool") == AgentEvent.PRE_TOOL_USE


def test_unknown_event_raises() -> None:
    with pytest.raises(ValueError, match="Unknown Acme event"):
        AcmeAdapter().translate_event("nope")


def test_normalizes_bash() -> None:
    assert AcmeAdapter().normalize_tool_name("Bash") == NormalizedTool.SHELL.value


def test_install_is_idempotent(tmp_path) -> None:
    adapter = AcmeAdapter()
    adapter.install_hooks(str(tmp_path), cmd="agentlint")
    adapter.install_hooks(str(tmp_path), cmd="agentlint")
    data = json.loads(_hooks_path("project", str(tmp_path)).read_text())
    assert len(data["hooks"]["beforeTool"]) == 1


def test_check_blocks_force_push(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AGENTLINT_SESSION_ID", "test-acme")
    monkeypatch.setenv("HOME", str(tmp_path))
    payload = {"tool_name": "Bash", "tool_input": {"command": "git push --force origin main"}}
    result = CliRunner().invoke(
        main,
        ["check", "--adapter", "acme", "--event", "beforeTool", "--project-dir", str(tmp_path)],
        input=json.dumps(payload),
    )
    assert result.exit_code == 1  # PlainJsonFormatter exits 1 on ERROR
    assert json.loads(result.output)["blocked"] is True
```

Also run the full suite: `tests/test_cli.py` iterates over `_HOOK_PLATFORMS`.

```bash
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
```

### 7. Docs

- Add `docs/agents/acme.md` with install, verify and uninstall steps, and link
  it from [docs/README.md](README.md).
- Add the agent to the supported-agents list in the top-level `README.md`.
- Add a `CHANGELOG.md` entry.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the rest of the PR checklist and
[architecture.md](architecture.md) for where adapters sit in the system.
