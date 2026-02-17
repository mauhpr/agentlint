"""Tests for universal pack Stop rules."""
from __future__ import annotations

from pathlib import Path

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.universal.no_debug_artifacts import NoDebugArtifacts
from agentlint.packs.universal.no_todo_left import NoTodoLeft
from agentlint.packs.universal.test_with_changes import TestWithChanges


def _stop_ctx(project_dir: str = "/tmp/project") -> RuleContext:
    return RuleContext(
        event=HookEvent.STOP,
        tool_name="",
        tool_input={},
        project_dir=project_dir,
    )


# ---------------------------------------------------------------------------
# NoDebugArtifacts
# ---------------------------------------------------------------------------


class TestNoDebugArtifacts:
    rule = NoDebugArtifacts()

    def test_detects_console_log(self, tmp_path: Path):
        js_file = tmp_path / "app.js"
        js_file.write_text('console.log("debug");\nconst x = 1;\n')
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(js_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "console.log()" in violations[0].message

    def test_detects_print_in_python(self, tmp_path: Path):
        py_file = tmp_path / "main.py"
        py_file.write_text('print("debug value")\nx = 1\n')
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(py_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "print()" in violations[0].message

    def test_detects_debugger_keyword(self, tmp_path: Path):
        ts_file = tmp_path / "app.ts"
        ts_file.write_text("function foo() {\n  debugger\n  return 1;\n}\n")
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(ts_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "debugger" in violations[0].message

    def test_detects_breakpoint(self, tmp_path: Path):
        py_file = tmp_path / "service.py"
        py_file.write_text("def run():\n    breakpoint()\n    return True\n")
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(py_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "breakpoint()" in violations[0].message

    def test_detects_pdb(self, tmp_path: Path):
        py_file = tmp_path / "handler.py"
        py_file.write_text("import pdb\ndef run():\n    pdb.set_trace()\n    return True\n")
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(py_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "pdb.set_trace()" in violations[0].message

    def test_ignores_test_files(self, tmp_path: Path):
        test_file = tmp_path / "test_main.py"
        test_file.write_text('print("test output")\n')
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(test_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_test_directory(self, tmp_path: Path):
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "conftest.py"
        test_file.write_text('print("setup")\n')
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(test_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_no_changed_files(self):
        ctx = _stop_ctx()
        ctx.session_state = {}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# NoTodoLeft
# ---------------------------------------------------------------------------


class TestNoTodoLeft:
    rule = NoTodoLeft()

    def test_detects_todo_comments(self, tmp_path: Path):
        py_file = tmp_path / "module.py"
        py_file.write_text("# TODO implement this\ndef foo():\n    pass\n")
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(py_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.INFO
        assert "1" in violations[0].message

    def test_detects_fixme(self, tmp_path: Path):
        js_file = tmp_path / "app.js"
        js_file.write_text("// FIXME broken\n// HACK workaround\nconst x = 1;\n")
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(js_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "2" in violations[0].message

    def test_detects_hack_and_xxx(self, tmp_path: Path):
        py_file = tmp_path / "util.py"
        py_file.write_text("# HACK temporary\n# XXX needs review\nx = 1\n")
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(py_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "2" in violations[0].message

    def test_ignores_non_comment_todo(self, tmp_path: Path):
        py_file = tmp_path / "readme.py"
        py_file.write_text('message = "TODO list app"\n')
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(py_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_block_comment_todo(self, tmp_path: Path):
        js_file = tmp_path / "main.js"
        js_file.write_text("/* TODO fix this */\nconst x = 1;\n")
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": [str(js_file)]}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_no_changed_files(self):
        ctx = _stop_ctx()
        ctx.session_state = {}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# TestWithChanges
# ---------------------------------------------------------------------------


class TestTestWithChanges:
    rule = TestWithChanges()

    def test_warns_source_changed_without_tests(self):
        ctx = _stop_ctx()
        ctx.session_state = {
            "changed_files": [
                "/project/src/main.py",
                "/project/src/utils.ts",
            ]
        }
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING
        assert "2" in violations[0].message

    def test_passes_when_tests_also_changed(self):
        ctx = _stop_ctx()
        ctx.session_state = {
            "changed_files": [
                "/project/src/main.py",
                "/project/tests/test_main.py",
            ]
        }
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_config_files(self):
        ctx = _stop_ctx()
        ctx.session_state = {
            "changed_files": [
                "/project/settings.py",
                "/project/config.py",
            ]
        }
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_no_changed_files(self):
        ctx = _stop_ctx()
        ctx.session_state = {"changed_files": []}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_only_test_files_changed(self):
        ctx = _stop_ctx()
        ctx.session_state = {
            "changed_files": [
                "/project/tests/test_main.py",
            ]
        }
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_source_extensions(self):
        ctx = _stop_ctx()
        ctx.session_state = {
            "changed_files": [
                "/project/README.md",
                "/project/data.json",
            ]
        }
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0
