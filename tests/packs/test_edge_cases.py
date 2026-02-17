"""Edge case tests for rules: empty content, long lines, BOM, whitespace-only."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.universal.max_file_size import MaxFileSize
from agentlint.packs.universal.no_secrets import NoSecrets
from agentlint.packs.universal.no_debug_artifacts import NoDebugArtifacts
from agentlint.packs.universal.no_todo_left import NoTodoLeft


def _pre_ctx(tool_name: str, tool_input: dict, content: str | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
        file_content=content,
    )


def _post_ctx(tool_name: str, tool_input: dict, content: str | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
        file_content=content,
    )


class TestEmptyContent:
    def test_no_secrets_empty_content(self):
        ctx = _pre_ctx("Write", {"file_path": "test.py", "content": ""})
        assert NoSecrets().evaluate(ctx) == []

    def test_no_secrets_whitespace_only(self):
        ctx = _pre_ctx("Write", {"file_path": "test.py", "content": "   \n\t\n  "})
        assert NoSecrets().evaluate(ctx) == []

    def test_max_file_size_empty_content(self):
        ctx = _post_ctx("Write", {"file_path": "test.py"}, content="")
        assert MaxFileSize().evaluate(ctx) == []

    def test_max_file_size_none_content(self):
        ctx = _post_ctx("Write", {"file_path": "test.py"}, content=None)
        assert MaxFileSize().evaluate(ctx) == []


class TestLongLines:
    def test_no_secrets_very_long_line(self):
        """10K+ character line should not crash."""
        long_line = "x = " + "a" * 10000
        ctx = _pre_ctx("Write", {"file_path": "test.py", "content": long_line})
        assert NoSecrets().evaluate(ctx) == []

    def test_max_file_size_single_long_line(self):
        """One very long line counts as 1 line."""
        ctx = _post_ctx("Write", {"file_path": "test.py"}, content="x" * 10000)
        assert MaxFileSize().evaluate(ctx) == []  # 1 line < 500 limit


class TestBOMMarkers:
    def test_no_secrets_with_bom(self):
        """UTF-8 BOM prefix should not cause false positives."""
        content = "\ufeffdef hello():\n    return 'world'\n"
        ctx = _pre_ctx("Write", {"file_path": "test.py", "content": content})
        assert NoSecrets().evaluate(ctx) == []


class TestStopRulesEmptyChangedFiles:
    def test_no_debug_artifacts_empty_changed_files(self):
        ctx = RuleContext(
            event=HookEvent.STOP,
            tool_name="",
            tool_input={},
            project_dir="/tmp",
            session_state={"changed_files": []},
        )
        assert NoDebugArtifacts().evaluate(ctx) == []

    def test_no_todo_left_no_session_state(self):
        ctx = RuleContext(
            event=HookEvent.STOP,
            tool_name="",
            tool_input={},
            project_dir="/tmp",
            session_state={},
        )
        assert NoTodoLeft().evaluate(ctx) == []

    def test_no_debug_artifacts_nonexistent_file(self, tmp_path):
        ctx = RuleContext(
            event=HookEvent.STOP,
            tool_name="",
            tool_input={},
            project_dir=str(tmp_path),
            session_state={"changed_files": [str(tmp_path / "does_not_exist.py")]},
        )
        assert NoDebugArtifacts().evaluate(ctx) == []

    def test_no_todo_left_nonexistent_file(self, tmp_path):
        ctx = RuleContext(
            event=HookEvent.STOP,
            tool_name="",
            tool_input={},
            project_dir=str(tmp_path),
            session_state={"changed_files": [str(tmp_path / "gone.py")]},
        )
        assert NoTodoLeft().evaluate(ctx) == []
