"""Tests for the file-scope governance rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.universal.file_scope import FileScope


def _make_context(
    tool_name: str = "Write",
    file_path: str | None = "/project/src/app.py",
    command: str | None = None,
    project_dir: str = "/project",
    config: dict | None = None,
) -> RuleContext:
    tool_input: dict = {}
    if file_path:
        tool_input["file_path"] = file_path
    if command:
        tool_input["command"] = command
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir=project_dir,
        config=config or {},
    )


class TestFileScopeInactive:
    def test_no_config_returns_empty(self):
        rule = FileScope()
        ctx = _make_context()
        assert rule.evaluate(ctx) == []

    def test_empty_allow_and_deny_returns_empty(self):
        rule = FileScope()
        ctx = _make_context(config={"file-scope": {"allow": [], "deny": []}})
        assert rule.evaluate(ctx) == []


class TestFileScopeAllow:
    def test_file_in_allowed_path(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        f = src / "app.py"
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"allow": ["src/**"]}},
        )
        assert rule.evaluate(ctx) == []

    def test_file_not_in_allowed_path(self, tmp_path):
        f = tmp_path / "secrets.env"
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"allow": ["src/**", "tests/**"]}},
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_multiple_allow_patterns(self, tmp_path):
        tests = tmp_path / "tests"
        tests.mkdir()
        f = tests / "test_app.py"
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"allow": ["src/**", "tests/**"]}},
        )
        assert rule.evaluate(ctx) == []


class TestFileScopeDeny:
    def test_denied_file_blocked(self, tmp_path):
        f = tmp_path / ".env"
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"deny": ["*.env"]}},
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "file-scope" in violations[0].rule_id

    def test_deny_takes_precedence_over_allow(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        f = src / "secrets.env"
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"allow": ["src/**"], "deny": ["*.env"]}},
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_deny_with_directory_glob(self, tmp_path):
        creds = tmp_path / "credentials"
        creds.mkdir()
        f = creds / "db.json"
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"deny": ["credentials/**"]}},
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_not_denied_file_passes(self, tmp_path):
        f = tmp_path / "src" / "app.py"
        f.parent.mkdir()
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"deny": ["*.env", "credentials/**"]}},
        )
        assert rule.evaluate(ctx) == []

    def test_custom_deny_message(self, tmp_path):
        f = tmp_path / ".env"
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"deny": ["*.env"], "deny_message": "Hands off!"}},
        )
        violations = rule.evaluate(ctx)
        assert "Hands off!" in violations[0].message


class TestFileScopePathTraversal:
    def test_traversal_blocked(self, tmp_path):
        rule = FileScope()
        traversal_path = str(tmp_path / "src" / ".." / ".." / "etc" / "passwd")
        ctx = _make_context(
            file_path=traversal_path,
            project_dir=str(tmp_path),
            config={"file-scope": {"allow": ["src/**"]}},
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_absolute_path_outside_project(self, tmp_path):
        rule = FileScope()
        ctx = _make_context(
            file_path="/etc/passwd",
            project_dir=str(tmp_path),
            config={"file-scope": {"allow": ["src/**"]}},
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1


class TestFileScopeToolTypes:
    def test_edit_tool_checked(self, tmp_path):
        f = tmp_path / ".env"
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            tool_name="Edit",
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"deny": ["*.env"]}},
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_read_tool_checked(self, tmp_path):
        f = tmp_path / ".env"
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            tool_name="Read",
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"deny": ["*.env"]}},
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_bash_cat_checked(self, tmp_path):
        rule = FileScope()
        ctx = _make_context(
            tool_name="Bash",
            file_path=None,
            command="cat /etc/passwd",
            project_dir=str(tmp_path),
            config={"file-scope": {"deny": ["/etc/**"]}},
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_bash_rm_checked(self, tmp_path):
        rule = FileScope()
        ctx = _make_context(
            tool_name="Bash",
            file_path=None,
            command="rm -rf /boot/vmlinuz",
            project_dir=str(tmp_path),
            config={"file-scope": {"deny": ["/boot/**"]}},
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_bash_safe_command_passes(self, tmp_path):
        rule = FileScope()
        ctx = _make_context(
            tool_name="Bash",
            file_path=None,
            command="git status",
            project_dir=str(tmp_path),
            config={"file-scope": {"deny": ["*.env"]}},
        )
        assert rule.evaluate(ctx) == []

    def test_no_file_path_returns_empty(self):
        rule = FileScope()
        ctx = _make_context(
            tool_name="Write",
            file_path=None,
            config={"file-scope": {"deny": ["*.env"]}},
        )
        assert rule.evaluate(ctx) == []


class TestFileScopeViolationDetails:
    def test_violation_has_file_path(self, tmp_path):
        f = tmp_path / ".env"
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"deny": ["*.env"]}},
        )
        violations = rule.evaluate(ctx)
        assert violations[0].file_path == str(f)

    def test_violation_has_suggestion(self, tmp_path):
        f = tmp_path / ".env"
        f.touch()
        rule = FileScope()
        ctx = _make_context(
            file_path=str(f),
            project_dir=str(tmp_path),
            config={"file-scope": {"deny": ["*.env"]}},
        )
        violations = rule.evaluate(ctx)
        assert violations[0].suggestion is not None
