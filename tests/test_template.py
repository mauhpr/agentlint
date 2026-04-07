"""Tests for agentlint.template — placeholder resolution and security."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext
from agentlint.template import build_template_context, is_path_within_project, resolve_template


def _make_context(
    file_path: str | None = "/project/src/app.py",
    project_dir: str = "/project",
    tool_name: str = "Write",
    session_state: dict | None = None,
) -> RuleContext:
    tool_input = {"file_path": file_path} if file_path else {}
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir=project_dir,
        session_state=session_state or {},
    )


class TestIsPathWithinProject:
    def test_file_inside_project(self, tmp_path):
        f = tmp_path / "src" / "app.py"
        f.parent.mkdir()
        f.touch()
        assert is_path_within_project(str(f), str(tmp_path)) is True

    def test_file_outside_project(self, tmp_path):
        assert is_path_within_project("/etc/passwd", str(tmp_path)) is False

    def test_traversal_blocked(self, tmp_path):
        traversal = str(tmp_path / "src" / ".." / ".." / "etc" / "passwd")
        assert is_path_within_project(traversal, str(tmp_path)) is False


class TestBuildTemplateContext:
    def test_file_placeholders(self, tmp_path):
        f = tmp_path / "src" / "app.py"
        f.parent.mkdir()
        f.touch()
        ctx = _make_context(file_path=str(f), project_dir=str(tmp_path))
        result = build_template_context(ctx)

        assert result["file.path"] == str(f)
        assert result["file.name"] == "app.py"
        assert result["file.stem"] == "app"
        assert result["file.ext"] == "py"
        assert result["file.dir"] == str(f.parent)
        assert result["file.relative"] == "src/app.py"
        assert result["file.dir.relative"] == "src"

    def test_project_dir(self):
        ctx = _make_context(file_path=None, project_dir="/my/project")
        result = build_template_context(ctx)
        assert result["project.dir"] == "/my/project"

    def test_tool_name(self):
        ctx = _make_context(tool_name="Edit")
        result = build_template_context(ctx)
        assert result["tool.name"] == "Edit"

    def test_session_changed_files(self):
        ctx = _make_context(
            file_path=None,
            session_state={"files_touched": ["a.py", "b.py"]},
        )
        result = build_template_context(ctx)
        assert result["session.changed_files"] == "a.py b.py"

    def test_session_changed_files_empty(self):
        ctx = _make_context(file_path=None, session_state={})
        result = build_template_context(ctx)
        assert result["session.changed_files"] == ""

    def test_file_outside_project_excluded(self):
        ctx = _make_context(file_path="/etc/passwd", project_dir="/project")
        result = build_template_context(ctx)
        assert "file.path" not in result
        assert "file.name" not in result

    def test_no_file_path(self):
        ctx = _make_context(file_path=None)
        result = build_template_context(ctx)
        assert "file.path" not in result


class TestResolveTemplate:
    def test_no_placeholders(self):
        result = resolve_template("echo hello", {})
        assert result == "echo hello"

    def test_single_placeholder(self):
        result = resolve_template("ruff check {file.path}", {"file.path": "/project/app.py"})
        # shlex.quote only adds quotes when needed (clean paths stay unquoted)
        assert result == "ruff check /project/app.py"

    def test_multiple_placeholders(self):
        ctx = {"file.path": "/p/a.py", "project.dir": "/p"}
        result = resolve_template("cmd {file.path} --root {project.dir}", ctx)
        assert result == "cmd /p/a.py --root /p"

    def test_missing_placeholder_returns_none(self):
        result = resolve_template("cmd {file.path}", {})
        assert result is None

    def test_env_placeholder(self, monkeypatch):
        monkeypatch.setenv("MY_FLAG", "--strict")
        result = resolve_template("ruff {env.MY_FLAG}", {})
        assert result == "ruff --strict"

    def test_env_missing_returns_empty(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
        result = resolve_template("cmd {env.NONEXISTENT_VAR}", {})
        assert result == "cmd ''"  # empty string gets quoted by shlex

    def test_env_never_causes_skip(self, monkeypatch):
        monkeypatch.delenv("MISSING", raising=False)
        result = resolve_template("cmd {env.MISSING}", {})
        assert result is not None  # env placeholders don't cause skip

    def test_mixed_env_and_missing_skips(self, monkeypatch):
        monkeypatch.setenv("OK", "val")
        result = resolve_template("cmd {env.OK} {file.path}", {})
        assert result is None  # file.path is missing → skip

    # --- Security tests ---

    def test_shell_injection_in_file_path(self):
        """Semicolons in file names are shell-escaped, preventing injection."""
        result = resolve_template(
            "ruff check {file.path}",
            {"file.path": "foo; rm -rf /; bar.py"},
        )
        assert result is not None
        # shlex.quote wraps the dangerous value in single quotes
        assert result == "ruff check 'foo; rm -rf /; bar.py'"

    def test_shell_injection_semicolon(self):
        result = resolve_template("cmd {file.name}", {"file.name": "a;whoami"})
        assert result == "cmd 'a;whoami'"

    def test_shell_injection_pipe(self):
        result = resolve_template("cmd {file.name}", {"file.name": "a|cat /etc/passwd"})
        assert result == "cmd 'a|cat /etc/passwd'"

    def test_shell_injection_backtick(self):
        result = resolve_template("cmd {file.name}", {"file.name": "`whoami`.py"})
        assert result == "cmd '`whoami`.py'"

    def test_shell_injection_dollar_paren(self):
        result = resolve_template("cmd {file.name}", {"file.name": "$(whoami).py"})
        assert result == "cmd '$(whoami).py'"

    def test_shell_injection_in_env_var(self, monkeypatch):
        monkeypatch.setenv("EVIL", "; rm -rf /")
        result = resolve_template("cmd {env.EVIL}", {})
        assert result == "cmd '; rm -rf /'"

    def test_clean_values_not_unnecessarily_quoted(self):
        """shlex.quote only adds quotes when the value contains shell metacharacters."""
        ctx = {
            "file.path": "/safe/path.py",
            "project.dir": "/safe",
            "tool.name": "Write",
        }
        result = resolve_template("{file.path} {project.dir} {tool.name}", ctx)
        assert result is not None
        # Clean values pass through unquoted
        assert result == "/safe/path.py /safe Write"

    def test_dangerous_values_are_quoted(self):
        """Values with shell metacharacters get quoted."""
        ctx = {"file.name": "has spaces.py"}
        result = resolve_template("cmd {file.name}", ctx)
        assert result == "cmd 'has spaces.py'"
