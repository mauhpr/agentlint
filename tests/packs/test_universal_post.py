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

    # --- v1.9.0: threshold-crossing tests (file_content_before) ---

    def test_pre_existing_large_file_no_fire(self):
        """Editing a pre-existing large file should NOT fire."""
        content_before = "line\n" * 1600
        content_after = "line\n" * 1603
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "big.py"},
            project_dir="/tmp/project",
            file_content=content_after,
            file_content_before=content_before,
        )
        assert self.rule.evaluate(ctx) == []

    def test_new_file_over_limit_fires(self):
        """New file (no file_content_before) over limit should fire."""
        content = "line\n" * 600
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "new.py"},
            project_dir="/tmp/project",
            file_content=content,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_file_crosses_threshold(self):
        """File going from 490 to 510 lines should fire (crosses 500 limit)."""
        content_before = "line\n" * 490
        content_after = "line\n" * 510
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "growing.py"},
            project_dir="/tmp/project",
            file_content=content_after,
            file_content_before=content_before,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_file_shrinks_still_over(self):
        """File shrinking from 600 to 550 (still over limit) should NOT fire."""
        content_before = "line\n" * 600
        content_after = "line\n" * 550
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "big.py"},
            project_dir="/tmp/project",
            file_content=content_after,
            file_content_before=content_before,
        )
        assert self.rule.evaluate(ctx) == []

    def test_file_shrinks_below_limit(self):
        """File shrinking from 550 to 490 (below limit) should NOT fire."""
        content_before = "line\n" * 550
        content_after = "line\n" * 490
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "shrinking.py"},
            project_dir="/tmp/project",
            file_content=content_after,
            file_content_before=content_before,
        )
        assert self.rule.evaluate(ctx) == []

    def test_file_content_before_none_fires(self):
        """None before (new file) with 600 lines after should fire."""
        content = "line\n" * 600
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "new.py"},
            project_dir="/tmp/project",
            file_content=content,
            file_content_before=None,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_file_content_before_empty_fires(self):
        """Empty string before with 600 lines after should fire."""
        content = "line\n" * 600
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "new.py"},
            project_dir="/tmp/project",
            file_content=content,
            file_content_before="",
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_custom_limit_pre_existing_exempt(self):
        """Custom limit=200, file 300 before, 303 after → no fire (pre-existing)."""
        content_before = "line\n" * 300
        content_after = "line\n" * 303
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "big.py"},
            project_dir="/tmp/project",
            file_content=content_after,
            file_content_before=content_before,
        )
        ctx.config = {"max-file-size": {"limit": 200}}
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_zero_line_change_large_file(self):
        """No change (600 before, 600 after) should NOT fire."""
        content = "line\n" * 600
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "stable.py"},
            project_dir="/tmp/project",
            file_content=content,
            file_content_before=content,
        )
        assert self.rule.evaluate(ctx) == []

    def test_exactly_at_limit_no_fire_and_crossing(self):
        """500 before, 500 after → no fire; 499 before, 501 after → fires."""
        content_at = "line\n" * 500
        ctx_at = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "exact.py"},
            project_dir="/tmp/project",
            file_content=content_at,
            file_content_before=content_at,
        )
        assert self.rule.evaluate(ctx_at) == []

        content_before = "line\n" * 499
        content_after = "line\n" * 501
        ctx_cross = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "crossing.py"},
            project_dir="/tmp/project",
            file_content=content_after,
            file_content_before=content_before,
        )
        violations = self.rule.evaluate(ctx_cross)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# DriftDetector
# ---------------------------------------------------------------------------


class TestDriftDetector:
    def _make_rule(self):
        return DriftDetector()

    def test_warns_after_threshold_edits(self):
        rule = self._make_rule()
        session_state: dict = {}
        for i in range(16):
            ctx = RuleContext(
                event=HookEvent.POST_TOOL_USE,
                tool_name="Write",
                tool_input={"file_path": f"file_{i}.py"},
                project_dir="/tmp/project",
                session_state=session_state,
            )
            violations = rule.evaluate(ctx)

        # After 16 edits without tests (default threshold=15), should warn.
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING
        assert "16" in violations[0].message

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
        # Only 1 unique file, well below threshold of 15.
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

    def test_fires_once_not_repeatedly(self):
        """After threshold is crossed, drift-detector fires once then stays silent."""
        rule = self._make_rule()
        session_state: dict = {}
        fire_count = 0
        # Edit 20 files (well above threshold of 15)
        for i in range(20):
            ctx = RuleContext(
                event=HookEvent.POST_TOOL_USE,
                tool_name="Write",
                tool_input={"file_path": f"file_{i}.py"},
                project_dir="/tmp/project",
                session_state=session_state,
            )
            violations = rule.evaluate(ctx)
            if violations:
                fire_count += 1
        # Should fire exactly once (on edit 16), not 5 times
        assert fire_count == 1

    def test_fire_once_resets_after_test_run(self):
        """After tests run, drift-detector can fire again on next threshold cross."""
        rule = self._make_rule()
        session_state: dict = {}

        # Cross threshold — fires once
        for i in range(16):
            ctx = RuleContext(
                event=HookEvent.POST_TOOL_USE,
                tool_name="Write",
                tool_input={"file_path": f"file_{i}.py"},
                project_dir="/tmp/project",
                session_state=session_state,
            )
            rule.evaluate(ctx)
        assert session_state.get("_drift_warned") is True

        # Run tests — resets
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "pytest -v"},
            project_dir="/tmp/project",
            session_state=session_state,
        )
        rule.evaluate(ctx)
        assert session_state.get("_drift_warned") is False

        # Cross threshold again — fires again
        fire_count = 0
        for i in range(16):
            ctx = RuleContext(
                event=HookEvent.POST_TOOL_USE,
                tool_name="Write",
                tool_input={"file_path": f"round2_{i}.py"},
                project_dir="/tmp/project",
                session_state=session_state,
            )
            violations = rule.evaluate(ctx)
            if violations:
                fire_count += 1
        assert fire_count == 1
