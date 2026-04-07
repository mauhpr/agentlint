"""Tests for the cli-integration rule — generic CLI subprocess execution."""
from __future__ import annotations

import subprocess

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.universal.cli_integration import CliIntegration


def _make_context(
    file_path: str = "/project/src/app.py",
    project_dir: str = "/project",
    tool_name: str = "Write",
    config: dict | None = None,
    session_state: dict | None = None,
) -> RuleContext:
    tool_input = {"file_path": file_path} if file_path else {}
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir=project_dir,
        config=config or {},
        session_state=session_state or {},
    )


def _config_with_commands(commands: list[dict]) -> dict:
    return {"cli-integration": {"commands": commands}}


class TestCliIntegrationNoConfig:
    def test_no_commands_configured(self):
        rule = CliIntegration()
        ctx = _make_context()
        assert rule.evaluate(ctx) == []

    def test_empty_commands_list(self):
        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([]))
        assert rule.evaluate(ctx) == []


class TestCliIntegrationSubprocess:
    def test_command_zero_exit_no_violation(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, stdout="ok", stderr=""),
        )
        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "echo", "command": "echo ok", "on": ["Write"], "glob": "**/*.py"},
        ]))
        assert rule.evaluate(ctx) == []

    def test_command_nonzero_exit_creates_violation(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, stdout="error on line 5", stderr=""),
        )
        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "ruff", "command": "ruff check {file.path}", "on": ["Write"], "glob": "**/*.py"},
        ]))
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].rule_id == "cli-integration/ruff"
        assert "error on line 5" in violations[0].message

    def test_command_uses_stderr_when_stdout_empty(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, stdout="", stderr="fatal error"),
        )
        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "cmd", "command": "cmd", "on": ["Write"], "glob": "**/*.py"},
        ]))
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "fatal error" in violations[0].message

    def test_command_timeout_skips_gracefully(self, monkeypatch):
        def _timeout(*a, **kw):
            raise subprocess.TimeoutExpired(cmd="slow", timeout=10)
        monkeypatch.setattr(subprocess, "run", _timeout)

        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "slow", "command": "sleep 999", "on": ["Write"], "glob": "**/*", "timeout": 1},
        ]))
        assert rule.evaluate(ctx) == []

    def test_command_not_found_skips(self, monkeypatch):
        def _not_found(*a, **kw):
            raise FileNotFoundError("No such file")
        monkeypatch.setattr(subprocess, "run", _not_found)

        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "missing", "command": "nonexistent_tool", "on": ["Write"], "glob": "**/*"},
        ]))
        assert rule.evaluate(ctx) == []

    def test_exit_zero_with_stderr_still_passes(self, monkeypatch):
        """Some tools write warnings to stderr even on success."""
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 0, stdout="", stderr="warning: something"),
        )
        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "tool", "command": "tool", "on": ["Write"], "glob": "**/*"},
        ]))
        assert rule.evaluate(ctx) == []

    def test_command_output_truncated(self, monkeypatch):
        long_output = "x" * 1000
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, stdout=long_output, stderr=""),
        )
        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "verbose", "command": "verbose", "on": ["Write"], "glob": "**/*"},
        ]))
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert len(violations[0].message) < 600
        assert violations[0].message.endswith("...")


class TestCliIntegrationFilters:
    def _pass_subprocess(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, stdout="fail", stderr=""),
        )

    def test_glob_filter_matches(self, monkeypatch):
        self._pass_subprocess(monkeypatch)
        rule = CliIntegration()
        ctx = _make_context(
            file_path="/project/src/app.py",
            config=_config_with_commands([
                {"name": "ruff", "command": "ruff", "on": ["Write"], "glob": "**/*.py"},
            ]),
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_glob_filter_rejects(self, monkeypatch):
        self._pass_subprocess(monkeypatch)
        rule = CliIntegration()
        ctx = _make_context(
            file_path="/project/src/app.py",
            config=_config_with_commands([
                {"name": "eslint", "command": "eslint", "on": ["Write"], "glob": "**/*.ts"},
            ]),
        )
        assert rule.evaluate(ctx) == []

    def test_on_filter_matches_tool_name(self, monkeypatch):
        self._pass_subprocess(monkeypatch)
        rule = CliIntegration()
        ctx = _make_context(
            tool_name="Edit",
            config=_config_with_commands([
                {"name": "ruff", "command": "ruff", "on": ["Write", "Edit"], "glob": "**/*.py"},
            ]),
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_on_filter_rejects_tool_name(self, monkeypatch):
        self._pass_subprocess(monkeypatch)
        rule = CliIntegration()
        ctx = _make_context(
            tool_name="Bash",
            config=_config_with_commands([
                {"name": "ruff", "command": "ruff", "on": ["Write", "Edit"], "glob": "**/*.py"},
            ]),
        )
        assert rule.evaluate(ctx) == []

    def test_default_on_is_write_edit(self, monkeypatch):
        self._pass_subprocess(monkeypatch)
        rule = CliIntegration()
        # No "on" key — should default to Write and Edit
        ctx = _make_context(
            tool_name="Write",
            config=_config_with_commands([
                {"name": "ruff", "command": "ruff", "glob": "**/*.py"},
            ]),
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_command_with_no_file_path_and_file_placeholder_skips(self, monkeypatch):
        self._pass_subprocess(monkeypatch)
        rule = CliIntegration()
        ctx = _make_context(
            file_path=None,
            config=_config_with_commands([
                {"name": "ruff", "command": "ruff check {file.path}", "on": ["Write"], "glob": "**/*"},
            ]),
        )
        # file.path placeholder can't resolve → command skipped
        assert rule.evaluate(ctx) == []

    def test_file_outside_project_dir_skips(self, monkeypatch):
        self._pass_subprocess(monkeypatch)
        rule = CliIntegration()
        ctx = _make_context(
            file_path="/etc/passwd",
            project_dir="/project",
            config=_config_with_commands([
                {"name": "ruff", "command": "ruff check {file.path}", "on": ["Write"], "glob": "**/*"},
            ]),
        )
        # file outside project → template context has no file.* → skip
        assert rule.evaluate(ctx) == []


class TestCliIntegrationConfig:
    def _fail_subprocess(self, monkeypatch):
        monkeypatch.setattr(
            subprocess, "run",
            lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, stdout="err", stderr=""),
        )

    def test_severity_config_error(self, monkeypatch):
        self._fail_subprocess(monkeypatch)
        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "strict", "command": "strict", "on": ["Write"], "glob": "**/*", "severity": "error"},
        ]))
        violations = rule.evaluate(ctx)
        assert violations[0].severity == Severity.ERROR

    def test_severity_config_info(self, monkeypatch):
        self._fail_subprocess(monkeypatch)
        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "advisory", "command": "advisory", "on": ["Write"], "glob": "**/*", "severity": "info"},
        ]))
        violations = rule.evaluate(ctx)
        assert violations[0].severity == Severity.INFO

    def test_default_severity_is_warning(self, monkeypatch):
        self._fail_subprocess(monkeypatch)
        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "default", "command": "default", "on": ["Write"], "glob": "**/*"},
        ]))
        violations = rule.evaluate(ctx)
        assert violations[0].severity == Severity.WARNING

    def test_default_timeout_is_10(self, monkeypatch):
        captured_kwargs = {}
        def _capture(*a, **kw):
            captured_kwargs.update(kw)
            return subprocess.CompletedProcess(a[0], 0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", _capture)

        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "tool", "command": "tool", "on": ["Write"], "glob": "**/*"},
        ]))
        rule.evaluate(ctx)
        assert captured_kwargs.get("timeout") == 10

    def test_custom_timeout(self, monkeypatch):
        captured_kwargs = {}
        def _capture(*a, **kw):
            captured_kwargs.update(kw)
            return subprocess.CompletedProcess(a[0], 0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", _capture)

        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "slow", "command": "slow", "on": ["Write"], "glob": "**/*", "timeout": 30},
        ]))
        rule.evaluate(ctx)
        assert captured_kwargs.get("timeout") == 30

    def test_multiple_commands_all_run(self, monkeypatch):
        call_count = 0
        def _counting(*a, **kw):
            nonlocal call_count
            call_count += 1
            return subprocess.CompletedProcess(a[0], 1, stdout=f"fail {call_count}", stderr="")
        monkeypatch.setattr(subprocess, "run", _counting)

        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "ruff", "command": "ruff", "on": ["Write"], "glob": "**/*.py"},
            {"name": "mypy", "command": "mypy", "on": ["Write"], "glob": "**/*.py"},
        ]))
        violations = rule.evaluate(ctx)
        assert len(violations) == 2
        assert violations[0].rule_id == "cli-integration/ruff"
        assert violations[1].rule_id == "cli-integration/mypy"

    def test_command_without_name_skipped(self, monkeypatch):
        self._fail_subprocess(monkeypatch)
        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"command": "ruff", "on": ["Write"], "glob": "**/*"},  # no name
        ]))
        assert rule.evaluate(ctx) == []

    def test_violation_has_suggestion(self, monkeypatch):
        self._fail_subprocess(monkeypatch)
        rule = CliIntegration()
        ctx = _make_context(config=_config_with_commands([
            {"name": "ruff", "command": "ruff check {file.path}", "on": ["Write"], "glob": "**/*.py"},
        ]))
        violations = rule.evaluate(ctx)
        assert violations[0].suggestion is not None
        assert "ruff check {file.path}" in violations[0].suggestion


class TestCliIntegrationSecurity:
    def test_shell_injection_via_filename_prevented(self, monkeypatch):
        """File named with shell metacharacters should be safely quoted."""
        captured_commands = []
        def _capture(*a, **kw):
            captured_commands.append(a[0])
            return subprocess.CompletedProcess(a[0], 0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", _capture)

        rule = CliIntegration()
        ctx = _make_context(
            file_path="/project/src/foo;whoami;.py",
            config=_config_with_commands([
                {"name": "ruff", "command": "ruff check {file.path}", "on": ["Write"], "glob": "**/*"},
            ]),
        )
        rule.evaluate(ctx)
        assert len(captured_commands) == 1
        # The semicolon must be quoted, not interpreted as shell separator
        assert ";" not in captured_commands[0].replace("'", "").replace(";", "", 1) or \
               "'" in captured_commands[0]

    def test_subprocess_runs_in_project_dir(self, monkeypatch):
        captured_kwargs = {}
        def _capture(*a, **kw):
            captured_kwargs.update(kw)
            return subprocess.CompletedProcess(a[0], 0, stdout="", stderr="")
        monkeypatch.setattr(subprocess, "run", _capture)

        rule = CliIntegration()
        ctx = _make_context(
            project_dir="/my/project",
            config=_config_with_commands([
                {"name": "tool", "command": "tool", "on": ["Write"], "glob": "**/*"},
            ]),
        )
        rule.evaluate(ctx)
        assert captured_kwargs.get("cwd") == "/my/project"
