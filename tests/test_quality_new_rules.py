"""Tests for new quality rules: no-large-diff, no-file-creation-sprawl, naming-conventions."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.quality.naming_conventions import NamingConventions
from agentlint.packs.quality.no_file_creation_sprawl import NoFileCreationSprawl
from agentlint.packs.quality.no_large_diff import NoLargeDiff


def _make_context(
    tool_name: str = "Write",
    file_path: str | None = "/project/src/app.py",
    file_content: str | None = None,
    file_content_before: str | None = None,
    config: dict | None = None,
    session_state: dict | None = None,
) -> RuleContext:
    tool_input = {"file_path": file_path} if file_path else {}
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/project",
        file_content=file_content,
        file_content_before=file_content_before,
        config=config or {},
        session_state=session_state if session_state is not None else {},
    )


# === no-large-diff ===

class TestNoLargeDiff:
    def test_small_edit_passes(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 50,
            file_content_before="line\n" * 40,
        )
        assert rule.evaluate(ctx) == []

    def test_large_addition_warns(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 300,
            file_content_before="line\n" * 10,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "290 lines added" in violations[0].message

    def test_large_removal_warns(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 10,
            file_content_before="line\n" * 200,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "190 lines removed" in violations[0].message

    def test_new_file_counts_as_addition(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 300,
            file_content_before=None,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "300 lines added" in violations[0].message

    def test_custom_thresholds(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 60,
            file_content_before="line\n" * 10,
            config={"no-large-diff": {"max_lines_added": 30}},
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_default_threshold_200(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 201,
            file_content_before="",
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_exactly_at_threshold_passes(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 200,
            file_content_before="",
        )
        assert rule.evaluate(ctx) == []

    def test_non_write_edit_ignored(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            tool_name="Bash",
            file_content="line\n" * 500,
            file_content_before="",
        )
        assert rule.evaluate(ctx) == []

    def test_no_file_content_passes(self):
        rule = NoLargeDiff()
        ctx = _make_context(file_content=None)
        assert rule.evaluate(ctx) == []

    def test_edit_tool_checked(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            tool_name="Edit",
            file_content="line\n" * 300,
            file_content_before="line\n" * 10,
        )
        assert len(rule.evaluate(ctx)) == 1


# === no-file-creation-sprawl ===

class TestNoFileCreationSprawl:
    def test_first_file_passes(self):
        rule = NoFileCreationSprawl()
        ctx = _make_context(
            file_path="/project/src/new.py",
            file_content_before=None,
            session_state={},
        )
        assert rule.evaluate(ctx) == []

    def test_warns_after_threshold(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(10)]}
        ctx = _make_context(
            file_path="/project/f10.py",
            file_content_before=None,
            session_state=state,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "11 new files" in violations[0].message

    def test_editing_existing_file_not_counted(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(10)]}
        ctx = _make_context(
            file_path="/project/existing.py",
            file_content_before="old content",  # exists = not new
            session_state=state,
        )
        assert rule.evaluate(ctx) == []

    def test_custom_threshold(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(3)]}
        ctx = _make_context(
            file_path="/project/f3.py",
            file_content_before=None,
            config={"no-file-creation-sprawl": {"max_new_files": 3}},
            session_state=state,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_non_write_tool_ignored(self):
        rule = NoFileCreationSprawl()
        ctx = _make_context(tool_name="Edit", file_content_before=None)
        assert rule.evaluate(ctx) == []

    def test_tracks_in_session_state(self):
        rule = NoFileCreationSprawl()
        state: dict = {}
        ctx = _make_context(
            file_path="/project/new.py",
            file_content_before=None,
            session_state=state,
        )
        rule.evaluate(ctx)
        assert "/project/new.py" in state["files_created"]

    def test_no_double_counting(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": ["/project/new.py"]}
        ctx = _make_context(
            file_path="/project/new.py",
            file_content_before=None,
            session_state=state,
        )
        rule.evaluate(ctx)
        assert state["files_created"].count("/project/new.py") == 1

    def test_no_file_path_passes(self):
        rule = NoFileCreationSprawl()
        ctx = _make_context(file_path=None, file_content_before=None)
        assert rule.evaluate(ctx) == []


# === naming-conventions ===

class TestNamingConventions:
    def _pre_context(self, file_path: str, config: dict | None = None) -> RuleContext:
        return RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": file_path},
            project_dir="/project",
            config=config or {},
        )

    def test_snake_case_python_passes(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/my_module.py")
        assert rule.evaluate(ctx) == []

    def test_camel_case_python_warns(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/MyModule.py")
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "snake_case" in violations[0].message

    def test_snake_case_ts_warns(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/my_utils.ts")
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "camelCase" in violations[0].message

    def test_camel_case_ts_passes(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/myUtils.ts")
        assert rule.evaluate(ctx) == []

    def test_pascal_case_tsx_passes(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/MyComponent.tsx")
        assert rule.evaluate(ctx) == []

    def test_snake_case_tsx_warns(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/my_component.tsx")
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "PascalCase" in violations[0].message

    def test_init_py_exempt(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/__init__.py")
        assert rule.evaluate(ctx) == []

    def test_test_files_exempt(self):
        rule = NamingConventions()
        assert rule.evaluate(self._pre_context("/project/tests/test_app.py")) == []
        assert rule.evaluate(self._pre_context("/project/src/app.test.ts")) == []
        assert rule.evaluate(self._pre_context("/project/src/app.spec.js")) == []

    def test_unknown_extension_passes(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/data/stuff.csv")
        assert rule.evaluate(ctx) == []

    def test_custom_convention_override(self):
        rule = NamingConventions()
        ctx = self._pre_context(
            "/project/src/MyModule.py",
            config={"naming-conventions": {"python": "PascalCase"}},
        )
        assert rule.evaluate(ctx) == []

    def test_suggestion_includes_example(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/MyModule.py")
        violations = rule.evaluate(ctx)
        assert violations[0].suggestion is not None
        assert "my_module.py" in violations[0].suggestion

    def test_non_write_edit_ignored(self):
        rule = NamingConventions()
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"file_path": "/project/src/BadName.py"},
            project_dir="/project",
        )
        assert rule.evaluate(ctx) == []

    def test_no_file_path_passes(self):
        rule = NamingConventions()
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={},
            project_dir="/project",
        )
        assert rule.evaluate(ctx) == []
