"""Tests for universal pack PostToolUse rules."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.universal.drift_detector import DriftDetector
from agentlint.packs.universal.max_file_size import MaxFileSize


def _post_ctx(file_path: str, content: str) -> RuleContext:
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": file_path},
        project_dir="/tmp/project",
        file_content=content,
    )


# ---------------------------------------------------------------------------
# MaxFileSize
# ---------------------------------------------------------------------------


class TestMaxFileSize:
    rule = MaxFileSize()

    def test_warns_large_file(self):
        content = "\n".join(f"line {i}" for i in range(600))
        ctx = _post_ctx("big_module.py", content)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING
        assert "600" in violations[0].message
        assert "+100 over" in violations[0].message

    def test_passes_small_file(self):
        content = "\n".join(f"line {i}" for i in range(100))
        ctx = _post_ctx("small.py", content)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_limit_from_config(self):
        content = "\n".join(f"line {i}" for i in range(250))
        ctx = _post_ctx("medium.py", content)
        ctx.config = {"max-file-size": {"limit": 200}}
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "250" in violations[0].message

    def test_ignores_non_write_tool(self):
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "ls"},
            project_dir="/tmp/project",
            file_content="x\n" * 1000,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_no_content(self):
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "x.py"},
            project_dir="/tmp/project",
            file_content=None,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_delta_shown_in_message(self):
        """Message should show +N over and suggestion should say how many lines to remove."""
        content = "\n".join(f"line {i}" for i in range(501))
        ctx = _post_ctx("big.py", content)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "+1 over" in violations[0].message
        assert "Remove 1 line" in violations[0].suggestion

    def test_delta_plural(self):
        content = "\n".join(f"line {i}" for i in range(550))
        ctx = _post_ctx("big.py", content)
        violations = self.rule.evaluate(ctx)
        assert "+50 over" in violations[0].message
        assert "Remove 50 lines" in violations[0].suggestion


# ---------------------------------------------------------------------------
# DriftDetector
# ---------------------------------------------------------------------------


class TestDriftDetector:
    def _make_rule(self):
        return DriftDetector()

    def test_warns_after_threshold_edits(self):
        rule = self._make_rule()
        session_state: dict = {}
        for i in range(11):
            ctx = RuleContext(
                event=HookEvent.POST_TOOL_USE,
                tool_name="Write",
                tool_input={"file_path": f"file_{i}.py"},
                project_dir="/tmp/project",
                session_state=session_state,
            )
            violations = rule.evaluate(ctx)

        # After 11 edits without tests, should warn.
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING
        assert "11" in violations[0].message

    def test_resets_after_test_run(self):
        rule = self._make_rule()
        session_state: dict = {}

        # Edit 8 files.
        for i in range(8):
            ctx = RuleContext(
                event=HookEvent.POST_TOOL_USE,
                tool_name="Write",
                tool_input={"file_path": f"file_{i}.py"},
                project_dir="/tmp/project",
                session_state=session_state,
            )
            rule.evaluate(ctx)

        # Run pytest.
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "pytest -v"},
            project_dir="/tmp/project",
            session_state=session_state,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 0
        assert session_state["edited_files"] == []
        assert session_state["last_test_run"] is True

        # Edit 5 more — should NOT warn (only 5, below threshold).
        for i in range(5):
            ctx = RuleContext(
                event=HookEvent.POST_TOOL_USE,
                tool_name="Write",
                tool_input={"file_path": f"file_new_{i}.py"},
                project_dir="/tmp/project",
                session_state=session_state,
            )
            violations = rule.evaluate(ctx)
        assert len(violations) == 0

    def test_same_file_edited_multiple_times_counts_once(self):
        rule = self._make_rule()
        session_state: dict = {}
        # Edit the same file 15 times — should count as 1 unique file.
        for i in range(15):
            ctx = RuleContext(
                event=HookEvent.POST_TOOL_USE,
                tool_name="Write",
                tool_input={"file_path": "same_file.py"},
                project_dir="/tmp/project",
                session_state=session_state,
            )
            violations = rule.evaluate(ctx)
        # Only 1 unique file, well below threshold of 10.
        assert len(violations) == 0
        assert len(session_state["edited_files"]) == 1

    def test_no_warning_below_threshold(self):
        rule = self._make_rule()
        session_state: dict = {}
        for i in range(5):
            ctx = RuleContext(
                event=HookEvent.POST_TOOL_USE,
                tool_name="Write",
                tool_input={"file_path": f"file_{i}.py"},
                project_dir="/tmp/project",
                session_state=session_state,
            )
            violations = rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_threshold_from_config(self):
        """Custom threshold from config should override default."""
        rule = self._make_rule()
        session_state: dict = {}
        for i in range(6):
            ctx = RuleContext(
                event=HookEvent.POST_TOOL_USE,
                tool_name="Write",
                tool_input={"file_path": f"file_{i}.py"},
                project_dir="/tmp/project",
                config={"drift-detector": {"threshold": 5}},
                session_state=session_state,
            )
            violations = rule.evaluate(ctx)
        # 6 edits with threshold=5 should trigger warning
        assert len(violations) == 1
        assert "6" in violations[0].message

    def test_config_file_not_counted(self):
        """Editing agentlint.yml should not count toward drift threshold."""
        rule = self._make_rule()
        session_state: dict = {}
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "agentlint.yml"},
            project_dir="/tmp/project",
            session_state=session_state,
        )
        rule.evaluate(ctx)
        assert len(session_state.get("edited_files", [])) == 0

    def test_python_file_counted(self):
        """Editing .py files should count toward drift threshold."""
        rule = self._make_rule()
        session_state: dict = {}
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "app.py"},
            project_dir="/tmp/project",
            session_state=session_state,
        )
        rule.evaluate(ctx)
        assert len(session_state.get("edited_files", [])) == 1

    def test_custom_extensions_config(self):
        """Custom extensions list should override defaults."""
        rule = self._make_rule()
        session_state: dict = {}
        # Only count .sql files
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "app.py"},
            project_dir="/tmp/project",
            config={"drift-detector": {"extensions": [".sql"]}},
            session_state=session_state,
        )
        rule.evaluate(ctx)
        assert len(session_state.get("edited_files", [])) == 0

        ctx2 = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "schema.sql"},
            project_dir="/tmp/project",
            config={"drift-detector": {"extensions": [".sql"]}},
            session_state=session_state,
        )
        rule.evaluate(ctx2)
        assert len(session_state.get("edited_files", [])) == 1

    def test_no_extensions_config_uses_default(self):
        """When no extensions config set, use default code extensions."""
        rule = self._make_rule()
        session_state: dict = {}
        for ext, should_count in [(".py", True), (".ts", True), (".md", False), (".yml", False)]:
            ctx = RuleContext(
                event=HookEvent.POST_TOOL_USE,
                tool_name="Write",
                tool_input={"file_path": f"file{ext}"},
                project_dir="/tmp/project",
                session_state=session_state,
            )
            rule.evaluate(ctx)
        # Only .py and .ts should be counted
        assert len(session_state.get("edited_files", [])) == 2
