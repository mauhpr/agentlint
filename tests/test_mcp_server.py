"""Tests for agentlint MCP server."""
from __future__ import annotations

import json

import pytest

from fastmcp import Client

from agentlint.mcp_server import mcp


@pytest.fixture
async def client(tmp_path, monkeypatch):
    """Create an MCP client connected to the agentlint server."""
    (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    async with Client(mcp) as c:
        yield c


class TestCheckContent:
    async def test_finds_secret(self, client):
        result = await client.call_tool(
            "check_content",
            {"content": 'API_KEY = "sk_live_abc123def456ghi789"', "file_path": "app.py"},
        )
        violations = json.loads(result.data)
        assert len(violations) > 0
        assert any(v["rule_id"] == "no-secrets" for v in violations)

    async def test_clean_content(self, client):
        result = await client.call_tool(
            "check_content",
            {"content": "def hello():\n    return 'world'\n", "file_path": "app.py"},
        )
        assert json.loads(result.data) == []

    async def test_custom_event(self, client):
        result = await client.call_tool(
            "check_content",
            {
                "content": "x = 1\n" * 600,
                "file_path": "big.py",
                "event": "PostToolUse",
            },
        )
        violations = json.loads(result.data)
        assert any(v["rule_id"] == "max-file-size" for v in violations)

    async def test_respects_config(self, tmp_path, monkeypatch):
        """Disabled rule should not fire."""
        (tmp_path / "agentlint.yml").write_text(
            "packs:\n  - universal\nrules:\n  no-secrets:\n    enabled: false\n"
        )
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        async with Client(mcp) as c:
            result = await c.call_tool(
                "check_content",
                {"content": 'SECRET = "sk_live_abc123def456ghi789"', "file_path": "app.py"},
            )
            violations = json.loads(result.data)
            assert not any(v["rule_id"] == "no-secrets" for v in violations)


    async def test_invalid_event_returns_error(self, client):
        """Invalid event string should return error, not crash."""
        result = await client.call_tool(
            "check_content",
            {"content": "x = 1", "file_path": "app.py", "event": "NotAValidEvent"},
        )
        data = json.loads(result.data)
        assert len(data) == 1
        assert "error" in data[0]

    async def test_bash_tool_name(self, client):
        """tool_name=Bash should check command against Bash rules."""
        result = await client.call_tool(
            "check_content",
            {
                "content": "git push --force origin main",
                "file_path": "",
                "tool_name": "Bash",
            },
        )
        violations = json.loads(result.data)
        assert any("no-force-push" in v["rule_id"] for v in violations)


class TestListRules:
    async def test_all_rules(self, client):
        result = await client.call_tool("list_rules", {})
        rules = json.loads(result.data)
        assert len(rules) >= 60
        assert all("id" in r and "pack" in r and "severity" in r for r in rules)

    async def test_filter_by_pack(self, client):
        result = await client.call_tool("list_rules", {"pack": "security"})
        rules = json.loads(result.data)
        assert len(rules) == 3
        assert all(r["pack"] == "security" for r in rules)


class TestGetConfig:
    async def test_returns_structure(self, client):
        result = await client.call_tool("get_config", {})
        config = json.loads(result.data)
        assert "severity" in config
        assert "packs" in config
        assert "universal" in config["packs"]


class TestWithCustomRules:
    async def test_check_content_with_custom_rules(self, tmp_path, monkeypatch):
        """check_content should evaluate custom rules when custom_rules_dir is set."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "my_rule.py").write_text(
            "from agentlint.models import Rule, RuleContext, Violation, HookEvent, Severity\n"
            "\n"
            "class AlwaysWarn(Rule):\n"
            "    id = 'custom-always-warn'\n"
            "    description = 'Always warns'\n"
            "    severity = Severity.WARNING\n"
            "    events = [HookEvent.PRE_TOOL_USE]\n"
            "    pack = 'universal'\n"
            "\n"
            "    def evaluate(self, context):\n"
            "        return [Violation(rule_id=self.id, message='custom fired', severity=self.severity)]\n"
        )
        (tmp_path / "agentlint.yml").write_text(
            "packs:\n  - universal\ncustom_rules_dir: rules/\n"
        )
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        async with Client(mcp) as c:
            result = await c.call_tool(
                "check_content",
                {"content": "x = 1", "file_path": "app.py"},
            )
            violations = json.loads(result.data)
            assert any(v["rule_id"] == "custom-always-warn" for v in violations)

    async def test_list_rules_includes_custom(self, tmp_path, monkeypatch):
        """list_rules should include custom rules."""
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "my_rule.py").write_text(
            "from agentlint.models import Rule, RuleContext, Violation, HookEvent, Severity\n"
            "\n"
            "class MyRule(Rule):\n"
            "    id = 'custom-test-rule'\n"
            "    description = 'Test rule'\n"
            "    severity = Severity.INFO\n"
            "    events = [HookEvent.PRE_TOOL_USE]\n"
            "    pack = 'mypack'\n"
            "\n"
            "    def evaluate(self, context):\n"
            "        return []\n"
        )
        (tmp_path / "agentlint.yml").write_text(
            "packs:\n  - universal\n  - mypack\ncustom_rules_dir: rules/\n"
        )
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        async with Client(mcp) as c:
            result = await c.call_tool("list_rules", {})
            rules = json.loads(result.data)
            assert any(r["id"] == "custom-test-rule" for r in rules)


class TestMonorepoMCP:
    async def test_check_content_resolves_project_packs(self, tmp_path, monkeypatch):
        """MCP check_content should use project-specific packs."""
        (tmp_path / "agentlint.yml").write_text(
            "packs:\n  - universal\n"
            "projects:\n  backend/:\n    packs: [universal, python]\n"
        )
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        (tmp_path / "backend").mkdir()
        async with Client(mcp) as c:
            result = await c.call_tool(
                "check_content",
                {
                    "content": "try:\n    pass\nexcept:\n    pass\n",
                    "file_path": str(tmp_path / "backend" / "app.py"),
                },
            )
            violations = json.loads(result.data)
            assert any(v["rule_id"] == "no-bare-except" for v in violations)


class TestResources:
    async def test_rules_resource(self, client):
        result = await client.read_resource("agentlint://rules")
        assert len(result) > 0
        # Resource returns TextResourceContents; parse the text
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        rules = json.loads(text)
        assert len(rules) >= 60

    async def test_config_resource(self, client):
        result = await client.read_resource("agentlint://config")
        assert len(result) > 0
        text = result[0].text if hasattr(result[0], "text") else str(result[0])
        config = json.loads(text)
        assert "packs" in config
