"""Tests for React pack rules."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.react.react_query_loading_state import ReactQueryLoadingState
from agentlint.packs.react.react_empty_state import ReactEmptyState
from agentlint.packs.react.react_lazy_loading import ReactLazyLoading


def _ctx(tool_name: str, tool_input: dict, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
        config=config or {},
    )


# ---------------------------------------------------------------------------
# ReactQueryLoadingState
# ---------------------------------------------------------------------------


class TestReactQueryLoadingState:
    rule = ReactQueryLoadingState()

    def test_detects_usequery_without_loading(self):
        ctx = _ctx("Write", {
            "file_path": "components/Users.tsx",
            "content": "const { data } = useQuery({ queryKey: ['users'] })",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1
        assert "loading" in violations[0].message

    def test_detects_usequery_without_error(self):
        ctx = _ctx("Write", {
            "file_path": "components/Users.tsx",
            "content": "const { data, isLoading } = useQuery({ queryKey: ['users'] })",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1
        assert "error" in violations[0].message

    def test_allows_usequery_with_both(self):
        ctx = _ctx("Write", {
            "file_path": "components/Users.tsx",
            "content": "const { data, isLoading, isError } = useQuery({ queryKey: ['users'] })",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_usequery_with_ispending(self):
        ctx = _ctx("Write", {
            "file_path": "components/Users.tsx",
            "content": "const { data, isPending, error } = useQuery({ queryKey: ['users'] })",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_usemutation_without_ispending(self):
        ctx = _ctx("Write", {
            "file_path": "components/Form.tsx",
            "content": "const { mutate } = useMutation({ mutationFn: createUser })",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1
        assert "useMutation" in violations[0].message

    def test_allows_usemutation_with_ispending(self):
        ctx = _ctx("Write", {
            "file_path": "components/Form.tsx",
            "content": "const { mutate, isPending } = useMutation({ mutationFn: createUser })",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_react_files(self):
        ctx = _ctx("Write", {
            "file_path": "hooks/useData.ts",
            "content": "const { data } = useQuery({ queryKey: ['users'] })",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_hooks_config(self):
        ctx = _ctx("Write", {
            "file_path": "components/Users.tsx",
            "content": "const { data } = useInfiniteQuery({ queryKey: ['users'] })",
        }, config={"hooks": ["useInfiniteQuery"]})
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1


# ---------------------------------------------------------------------------
# ReactEmptyState
# ---------------------------------------------------------------------------


class TestReactEmptyState:
    rule = ReactEmptyState()

    def test_detects_map_without_empty_state(self):
        ctx = _ctx("Write", {
            "file_path": "components/UserList.tsx",
            "content": "return <ul>{users.map(u => <li>{u.name}</li>)}</ul>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_map_with_length_check(self):
        ctx = _ctx("Write", {
            "file_path": "components/UserList.tsx",
            "content": "return users.length > 0 ? <ul>{users.map(u => <li>{u.name}</li>)}</ul> : <Empty />",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_map_with_guard(self):
        ctx = _ctx("Write", {
            "file_path": "components/UserList.tsx",
            "content": "return <ul>{users.length && users.map(u => <li>{u.name}</li>)}</ul>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_react_files(self):
        ctx = _ctx("Write", {
            "file_path": "utils/helpers.ts",
            "content": "items.map(x => x.id)",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_map_with_nearby_length(self):
        ctx = _ctx("Write", {
            "file_path": "components/List.tsx",
            "content": "if (items.length === 0) return null;\nreturn items.map(i => <div>{i}</div>)",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# ReactLazyLoading
# ---------------------------------------------------------------------------


class TestReactLazyLoading:
    rule = ReactLazyLoading()

    def test_detects_heavy_import_in_page(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Dashboard.tsx",
            "content": "import Chart from '@/components/Chart'\nimport { useState } from 'react'",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "Chart" in violations[0].message

    def test_allows_lazy_import(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Dashboard.tsx",
            "content": "const Chart = React.lazy(() => import('@/components/Chart'))\nreturn <Suspense><Chart /></Suspense>",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_lazy_without_suspense(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Dashboard.tsx",
            "content": "const Chart = React.lazy(() => import('@/components/Chart'))\nreturn <Chart />",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "Suspense" in violations[0].message

    def test_allows_heavy_import_in_non_page(self):
        ctx = _ctx("Write", {
            "file_path": "components/ChartWrapper.tsx",
            "content": "import Chart from '@/lib/Chart'",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_heavy_components(self):
        ctx = _ctx("Write", {
            "file_path": "pages/Analytics.tsx",
            "content": "import Plotly from 'plotly'",
        }, config={"heavy_components": ["Plotly"]})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ignores_non_react_files(self):
        ctx = _ctx("Write", {
            "file_path": "pages/index.ts",
            "content": "import Chart from 'chart'",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# Pack loader
# ---------------------------------------------------------------------------


class TestReactPackLoader:
    def test_load_react_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["react"])
        assert len(rules) == 3
        ids = {r.id for r in rules}
        assert "react-query-loading-state" in ids
        assert "react-empty-state" in ids
        assert "react-lazy-loading" in ids

    def test_all_rules_have_react_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["react"])
        for rule in rules:
            assert rule.pack == "react"
