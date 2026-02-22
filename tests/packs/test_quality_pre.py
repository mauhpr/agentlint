"""Tests for quality pack PreToolUse rules."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.quality.commit_message_format import CommitMessageFormat
from agentlint.packs.quality.no_error_handling_removal import NoErrorHandlingRemoval


def _ctx(
    tool_name: str = "Bash",
    tool_input: dict | None = None,
    config: dict | None = None,
    file_content: str | None = None,
    file_content_before: str | None = None,
) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input or {},
        project_dir="/tmp/project",
        config=config or {},
        file_content=file_content,
        file_content_before=file_content_before,
    )


# --- CommitMessageFormat ---


class TestCommitMessageFormat:
    rule = CommitMessageFormat()

    def test_valid_conventional_commit(self):
        ctx = _ctx(tool_input={"command": 'git commit -m "feat: add login flow"'})
        assert self.rule.evaluate(ctx) == []

    def test_valid_with_scope(self):
        ctx = _ctx(tool_input={"command": 'git commit -m "fix(auth): token refresh"'})
        assert self.rule.evaluate(ctx) == []

    def test_valid_with_breaking_change(self):
        ctx = _ctx(tool_input={"command": 'git commit -m "feat!: remove deprecated API"'})
        assert self.rule.evaluate(ctx) == []

    def test_invalid_format_warns(self):
        ctx = _ctx(tool_input={"command": 'git commit -m "updated the thing"'})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "conventional format" in violations[0].message

    def test_too_long_subject(self):
        long_msg = "feat: " + "x" * 80
        ctx = _ctx(tool_input={"command": f'git commit -m "{long_msg}"'})
        violations = self.rule.evaluate(ctx)
        assert any("exceeds" in v.message for v in violations)

    def test_custom_max_length(self):
        msg = "feat: " + "x" * 45  # 51 chars total
        ctx = _ctx(
            tool_input={"command": f'git commit -m "{msg}"'},
            config={"commit-message-format": {"max_subject_length": 50}},
        )
        violations = self.rule.evaluate(ctx)
        assert any("exceeds" in v.message for v in violations)

    def test_freeform_mode_skips_conventional_check(self):
        ctx = _ctx(
            tool_input={"command": 'git commit -m "updated the thing"'},
            config={"commit-message-format": {"format": "freeform"}},
        )
        assert self.rule.evaluate(ctx) == []

    def test_ignores_non_bash(self):
        ctx = _ctx(tool_name="Write", tool_input={"command": 'git commit -m "bad"'})
        assert self.rule.evaluate(ctx) == []

    def test_ignores_non_commit_commands(self):
        ctx = _ctx(tool_input={"command": "git push origin main"})
        assert self.rule.evaluate(ctx) == []

    def test_ignores_empty_command(self):
        ctx = _ctx(tool_input={})
        assert self.rule.evaluate(ctx) == []

    def test_single_quoted_message(self):
        ctx = _ctx(tool_input={"command": "git commit -m 'feat: add feature'"})
        assert self.rule.evaluate(ctx) == []

    def test_all_conventional_types(self):
        """All standard types should be accepted."""
        for type_ in ("feat", "fix", "chore", "docs", "refactor", "test", "ci", "style", "perf", "build", "revert"):
            ctx = _ctx(tool_input={"command": f'git commit -m "{type_}: something"'})
            assert self.rule.evaluate(ctx) == [], f"Type '{type_}' should be valid"


# --- NoErrorHandlingRemoval ---


class TestNoErrorHandlingRemoval:
    rule = NoErrorHandlingRemoval()

    def test_detects_python_try_removal(self):
        old = "try:\n    do_thing()\nexcept ValueError:\n    handle()\n"
        new = "do_thing()\n"
        ctx = _ctx(
            tool_name="Write",
            tool_input={"file_path": "app.py", "content": new},
            file_content=new,
            file_content_before=old,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "Error handling removed" in violations[0].message

    def test_allows_when_error_handling_preserved(self):
        old = "try:\n    do_thing()\nexcept ValueError:\n    handle()\n"
        new = "try:\n    do_thing()\n    extra()\nexcept ValueError:\n    handle()\n"
        ctx = _ctx(
            tool_name="Write",
            tool_input={"file_path": "app.py", "content": new},
            file_content=new,
            file_content_before=old,
        )
        assert self.rule.evaluate(ctx) == []

    def test_allows_when_no_previous_content(self):
        new = "do_thing()\n"
        ctx = _ctx(
            tool_name="Write",
            tool_input={"file_path": "app.py", "content": new},
            file_content=new,
        )
        assert self.rule.evaluate(ctx) == []

    def test_detects_js_catch_removal(self):
        old = "fetch(url).then(r => r.json()).catch(e => console.error(e));\n"
        new = "fetch(url).then(r => r.json());\n"
        ctx = _ctx(
            tool_name="Write",
            tool_input={"file_path": "app.ts", "content": new},
            file_content=new,
            file_content_before=old,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_detects_error_boundary_removal(self):
        old = "<ErrorBoundary fallback={<p>Error</p>}><App /></ErrorBoundary>\n"
        new = "<App />\n"
        ctx = _ctx(
            tool_name="Write",
            tool_input={"file_path": "app.tsx", "content": new},
            file_content=new,
            file_content_before=old,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_skips_test_files(self):
        old = "try:\n    do_thing()\nexcept ValueError:\n    handle()\n"
        new = "do_thing()\n"
        ctx = _ctx(
            tool_name="Write",
            tool_input={"file_path": "tests/test_app.py", "content": new},
            file_content=new,
            file_content_before=old,
        )
        assert self.rule.evaluate(ctx) == []

    def test_skips_non_code_files(self):
        ctx = _ctx(
            tool_name="Write",
            tool_input={"file_path": "README.md", "content": "text"},
            file_content="text",
            file_content_before="old text",
        )
        assert self.rule.evaluate(ctx) == []

    def test_ignores_non_file_tools(self):
        ctx = _ctx(tool_name="Bash", tool_input={"command": "echo hi"})
        assert self.rule.evaluate(ctx) == []

    def test_allows_reduction_not_complete_removal(self):
        """Reducing error handling (but not removing all) should not warn."""
        old = "try:\n    a()\nexcept:\n    pass\ntry:\n    b()\nexcept:\n    pass\n"
        new = "a()\ntry:\n    b()\nexcept:\n    pass\n"
        ctx = _ctx(
            tool_name="Write",
            tool_input={"file_path": "app.py", "content": new},
            file_content=new,
            file_content_before=old,
        )
        assert self.rule.evaluate(ctx) == []

    def test_python_none_check_removal(self):
        old = "if result is not None:\n    process(result)\n"
        new = "process(result)\n"
        ctx = _ctx(
            tool_name="Write",
            tool_input={"file_path": "app.py", "content": new},
            file_content=new,
            file_content_before=old,
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
