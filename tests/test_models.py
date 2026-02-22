"""Tests for agentlint core models."""
from __future__ import annotations

import pytest

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation


# --- Severity tests ---


class TestSeverity:
    def test_severity_values(self):
        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"

    def test_error_is_blocking(self):
        assert Severity.ERROR.is_blocking is True

    def test_warning_is_not_blocking(self):
        assert Severity.WARNING.is_blocking is False

    def test_info_is_not_blocking(self):
        assert Severity.INFO.is_blocking is False


# --- HookEvent tests ---


class TestHookEvent:
    def test_hook_event_values(self):
        assert HookEvent.PRE_TOOL_USE.value == "PreToolUse"
        assert HookEvent.POST_TOOL_USE.value == "PostToolUse"
        assert HookEvent.STOP.value == "Stop"
        assert HookEvent.SESSION_START.value == "SessionStart"
        assert HookEvent.SESSION_END.value == "SessionEnd"
        assert HookEvent.USER_PROMPT_SUBMIT.value == "UserPromptSubmit"
        assert HookEvent.SUB_AGENT_START.value == "SubagentStart"
        assert HookEvent.SUB_AGENT_STOP.value == "SubagentStop"
        assert HookEvent.NOTIFICATION.value == "Notification"
        assert HookEvent.PRE_COMPACT.value == "PreCompact"
        assert HookEvent.POST_TOOL_USE_FAILURE.value == "PostToolUseFailure"
        assert HookEvent.PERMISSION_REQUEST.value == "PermissionRequest"
        assert HookEvent.CONFIG_CHANGE.value == "ConfigChange"
        assert HookEvent.WORKTREE_CREATE.value == "WorktreeCreate"
        assert HookEvent.WORKTREE_REMOVE.value == "WorktreeRemove"
        assert HookEvent.TEAMMATE_IDLE.value == "TeammateIdle"
        assert HookEvent.TASK_COMPLETED.value == "TaskCompleted"

    def test_total_event_count(self):
        """Ensure we have all 17 hook events."""
        assert len(HookEvent) == 17

    def test_from_string_valid(self):
        assert HookEvent.from_string("PreToolUse") == HookEvent.PRE_TOOL_USE
        assert HookEvent.from_string("PostToolUse") == HookEvent.POST_TOOL_USE
        assert HookEvent.from_string("Stop") == HookEvent.STOP
        assert HookEvent.from_string("SessionStart") == HookEvent.SESSION_START

    def test_from_string_new_events(self):
        assert HookEvent.from_string("SessionEnd") == HookEvent.SESSION_END
        assert HookEvent.from_string("UserPromptSubmit") == HookEvent.USER_PROMPT_SUBMIT
        assert HookEvent.from_string("SubagentStart") == HookEvent.SUB_AGENT_START
        assert HookEvent.from_string("SubagentStop") == HookEvent.SUB_AGENT_STOP
        assert HookEvent.from_string("Notification") == HookEvent.NOTIFICATION
        assert HookEvent.from_string("PreCompact") == HookEvent.PRE_COMPACT
        assert HookEvent.from_string("PostToolUseFailure") == HookEvent.POST_TOOL_USE_FAILURE
        assert HookEvent.from_string("PermissionRequest") == HookEvent.PERMISSION_REQUEST
        assert HookEvent.from_string("ConfigChange") == HookEvent.CONFIG_CHANGE
        assert HookEvent.from_string("WorktreeCreate") == HookEvent.WORKTREE_CREATE
        assert HookEvent.from_string("WorktreeRemove") == HookEvent.WORKTREE_REMOVE
        assert HookEvent.from_string("TeammateIdle") == HookEvent.TEAMMATE_IDLE
        assert HookEvent.from_string("TaskCompleted") == HookEvent.TASK_COMPLETED

    def test_from_string_all_events_round_trip(self):
        """Every HookEvent member round-trips through from_string."""
        for member in HookEvent:
            assert HookEvent.from_string(member.value) == member

    def test_from_string_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown hook event: InvalidEvent"):
            HookEvent.from_string("InvalidEvent")


# --- Violation tests ---


class TestViolation:
    def test_creation_required_fields(self):
        v = Violation(rule_id="R001", message="bad thing", severity=Severity.ERROR)
        assert v.rule_id == "R001"
        assert v.message == "bad thing"
        assert v.severity == Severity.ERROR

    def test_optional_fields_default_to_none(self):
        v = Violation(rule_id="R001", message="bad thing", severity=Severity.ERROR)
        assert v.file_path is None
        assert v.line is None
        assert v.suggestion is None

    def test_creation_with_all_fields(self):
        v = Violation(
            rule_id="R002",
            message="something wrong",
            severity=Severity.WARNING,
            file_path="/tmp/foo.py",
            line=42,
            suggestion="fix it",
        )
        assert v.file_path == "/tmp/foo.py"
        assert v.line == 42
        assert v.suggestion == "fix it"

    def test_to_dict(self):
        v = Violation(
            rule_id="R001",
            message="bad thing",
            severity=Severity.ERROR,
            file_path="/tmp/foo.py",
            line=10,
            suggestion="do better",
        )
        d = v.to_dict()
        assert d == {
            "rule_id": "R001",
            "message": "bad thing",
            "severity": "error",
            "file_path": "/tmp/foo.py",
            "line": 10,
            "suggestion": "do better",
        }

    def test_to_dict_with_none_optional_fields(self):
        v = Violation(rule_id="R001", message="bad", severity=Severity.INFO)
        d = v.to_dict()
        assert d["file_path"] is None
        assert d["line"] is None
        assert d["suggestion"] is None
        assert d["severity"] == "info"


# --- RuleContext tests ---


class TestRuleContext:
    def test_creation(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "/tmp/test.py"},
            project_dir="/home/user/project",
        )
        assert ctx.event == HookEvent.PRE_TOOL_USE
        assert ctx.tool_name == "Write"
        assert ctx.project_dir == "/home/user/project"

    def test_file_path_from_tool_input(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "/tmp/test.py"},
            project_dir="/home/user/project",
        )
        assert ctx.file_path == "/tmp/test.py"

    def test_file_path_missing_from_tool_input(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "ls"},
            project_dir="/home/user/project",
        )
        assert ctx.file_path is None

    def test_command_from_tool_input(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "rm -rf /"},
            project_dir="/home/user/project",
        )
        assert ctx.command == "rm -rf /"

    def test_command_missing_from_tool_input(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "/tmp/test.py"},
            project_dir="/home/user/project",
        )
        assert ctx.command is None

    def test_file_content_default_none(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={},
            project_dir="/home/user/project",
        )
        assert ctx.file_content is None

    def test_file_content_provided(self):
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Read",
            tool_input={"file_path": "/tmp/test.py"},
            project_dir="/home/user/project",
            file_content="print('hello')",
        )
        assert ctx.file_content == "print('hello')"

    def test_config_default_empty_dict(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={},
            project_dir="/home/user/project",
        )
        assert ctx.config == {}

    def test_session_state_default_empty_dict(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={},
            project_dir="/home/user/project",
        )
        assert ctx.session_state == {}

    def test_prompt_field_default_none(self):
        ctx = RuleContext(
            event=HookEvent.USER_PROMPT_SUBMIT,
            tool_name="",
            tool_input={},
            project_dir="/home/user/project",
        )
        assert ctx.prompt is None

    def test_prompt_field_provided(self):
        ctx = RuleContext(
            event=HookEvent.USER_PROMPT_SUBMIT,
            tool_name="",
            tool_input={},
            project_dir="/home/user/project",
            prompt="delete everything",
        )
        assert ctx.prompt == "delete everything"

    def test_subagent_output_field(self):
        ctx = RuleContext(
            event=HookEvent.SUB_AGENT_STOP,
            tool_name="",
            tool_input={},
            project_dir="/home/user/project",
            subagent_output="task completed successfully",
        )
        assert ctx.subagent_output == "task completed successfully"

    def test_notification_type_field(self):
        ctx = RuleContext(
            event=HookEvent.NOTIFICATION,
            tool_name="",
            tool_input={},
            project_dir="/home/user/project",
            notification_type="warning",
        )
        assert ctx.notification_type == "warning"

    def test_compact_source_field(self):
        ctx = RuleContext(
            event=HookEvent.PRE_COMPACT,
            tool_name="",
            tool_input={},
            project_dir="/home/user/project",
            compact_source="auto",
        )
        assert ctx.compact_source == "auto"

    def test_file_content_before_field(self):
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Edit",
            tool_input={"file_path": "/tmp/test.py"},
            project_dir="/home/user/project",
            file_content="new content",
            file_content_before="old content",
        )
        assert ctx.file_content_before == "old content"
        assert ctx.file_content == "new content"

    def test_new_fields_all_default_none(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={},
            project_dir="/home/user/project",
        )
        assert ctx.prompt is None
        assert ctx.subagent_output is None
        assert ctx.notification_type is None
        assert ctx.compact_source is None
        assert ctx.file_content_before is None


# --- Rule tests ---


class TestRule:
    def test_rule_is_abstract(self):
        with pytest.raises(TypeError):
            Rule()  # type: ignore[abstract]

    def test_concrete_subclass_works(self):
        class MyRule(Rule):
            id = "TEST001"
            description = "A test rule"
            severity = Severity.WARNING
            events = [HookEvent.PRE_TOOL_USE]
            pack = "test"

            def evaluate(self, context: RuleContext) -> list[Violation]:
                return [
                    Violation(
                        rule_id=self.id,
                        message="test violation",
                        severity=self.severity,
                    )
                ]

        rule = MyRule()
        assert rule.id == "TEST001"
        assert rule.description == "A test rule"
        assert rule.severity == Severity.WARNING

    def test_evaluate_returns_violations(self):
        class MyRule(Rule):
            id = "TEST001"
            description = "A test rule"
            severity = Severity.ERROR
            events = [HookEvent.PRE_TOOL_USE]
            pack = "test"

            def evaluate(self, context: RuleContext) -> list[Violation]:
                return [
                    Violation(
                        rule_id=self.id,
                        message="found an issue",
                        severity=self.severity,
                    )
                ]

        rule = MyRule()
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "/tmp/test.py"},
            project_dir="/home/user/project",
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].rule_id == "TEST001"
        assert violations[0].message == "found an issue"

    def test_matches_event_true(self):
        class MyRule(Rule):
            id = "TEST001"
            description = "A test rule"
            severity = Severity.ERROR
            events = [HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE]
            pack = "test"

            def evaluate(self, context: RuleContext) -> list[Violation]:
                return []

        rule = MyRule()
        assert rule.matches_event(HookEvent.PRE_TOOL_USE) is True
        assert rule.matches_event(HookEvent.POST_TOOL_USE) is True

    def test_matches_event_false(self):
        class MyRule(Rule):
            id = "TEST001"
            description = "A test rule"
            severity = Severity.ERROR
            events = [HookEvent.PRE_TOOL_USE]
            pack = "test"

            def evaluate(self, context: RuleContext) -> list[Violation]:
                return []

        rule = MyRule()
        assert rule.matches_event(HookEvent.STOP) is False
        assert rule.matches_event(HookEvent.SESSION_START) is False


# --- Import from package tests ---


class TestPackageExports:
    def test_import_from_agentlint(self):
        from agentlint import HookEvent, Rule, RuleContext, Severity, Violation

        assert Severity is not None
        assert HookEvent is not None
        assert Violation is not None
        assert RuleContext is not None
        assert Rule is not None
