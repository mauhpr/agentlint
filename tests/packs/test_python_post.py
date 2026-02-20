"""Tests for Python pack PostToolUse rules."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.python.no_unnecessary_async import NoUnnecessaryAsync


def _ctx(tool_name: str, tool_input: dict, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
        config=config or {},
    )


class TestNoUnnecessaryAsync:
    rule = NoUnnecessaryAsync()

    def test_detects_async_without_await(self):
        ctx = _ctx("Write", {
            "file_path": "app/service.py",
            "content": "async def fetch_data():\n    return get_data()",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.INFO
        assert "fetch_data" in violations[0].message

    def test_allows_async_with_await(self):
        ctx = _ctx("Write", {
            "file_path": "app/service.py",
            "content": "async def fetch_data():\n    return await get_data()",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_abstract_methods(self):
        ctx = _ctx("Write", {
            "file_path": "app/service.py",
            "content": "@abstractmethod\nasync def fetch_data(self):\n    pass",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_property_decorator(self):
        ctx = _ctx("Write", {
            "file_path": "app/service.py",
            "content": "@property\nasync def value(self):\n    return self._value",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_override_decorator(self):
        ctx = _ctx("Write", {
            "file_path": "app/service.py",
            "content": "@override\nasync def handle(self):\n    return self.default()",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_stub_pass(self):
        ctx = _ctx("Write", {
            "file_path": "app/service.py",
            "content": "async def fetch_data():\n    pass",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_stub_ellipsis(self):
        ctx = _ctx("Write", {
            "file_path": "app/service.py",
            "content": "async def fetch_data():\n    ...",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_stub_not_implemented(self):
        ctx = _ctx("Write", {
            "file_path": "app/service.py",
            "content": "async def fetch_data():\n    raise NotImplementedError",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_test_files(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_service.py",
            "content": "async def test_fetch():\n    result = fetch()",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_python(self):
        ctx = _ctx("Write", {
            "file_path": "app/service.js",
            "content": "async def fetch_data():\n    return 1",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_write_tools(self):
        ctx = _ctx("Read", {"file_path": "app/service.py"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_ignore_decorators(self):
        ctx = _ctx("Write", {
            "file_path": "app/service.py",
            "content": "@app.route('/api')\nasync def handler():\n    return response()",
        }, config={"ignore_decorators": ["route"]})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_multiple_functions(self):
        ctx = _ctx("Write", {
            "file_path": "app/service.py",
            "content": (
                "async def good():\n    return await fetch()\n\n"
                "async def bad():\n    return compute()\n"
            ),
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "bad" in violations[0].message
