"""Tests for universal pack PreToolUse rules."""
from __future__ import annotations

import pytest

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.universal.dependency_hygiene import DependencyHygiene
from agentlint.packs.universal.no_destructive_commands import NoDestructiveCommands
from agentlint.packs.universal.no_env_commit import NoEnvCommit
from agentlint.packs.universal.no_force_push import NoForcePush
from agentlint.packs.universal.no_secrets import NoSecrets


def _ctx(tool_name: str, tool_input: dict) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
    )


# ---------------------------------------------------------------------------
# NoSecrets
# ---------------------------------------------------------------------------


class TestNoSecrets:
    rule = NoSecrets()

    def test_blocks_api_key_in_write(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'api_key = "sk_live_abc123xyz456789012"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1
        assert any("secret" in v.message.lower() or "api_key" in v.message.lower() for v in violations)

    def test_blocks_password_assignment(self):
        ctx = _ctx("Write", {
            "file_path": "settings.py",
            "content": 'password = "SuperS3cretP@ssw0rd!!"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_blocks_bearer_token(self):
        ctx = _ctx("Edit", {
            "file_path": "app.py",
            "content": 'headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"}',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_blocks_aws_key(self):
        ctx = _ctx("Write", {
            "file_path": "deploy.py",
            "content": "aws_key = 'AKIAIOSFODNN7EXAMPLE'",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_blocks_github_token(self):
        ctx = _ctx("Write", {
            "file_path": "ci.py",
            "content": "token = 'ghp_ABCDEFghijklmnopqrstuvwxyz1234567890'",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_allows_env_var_reference(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'api_key = os.environ["MY_API_KEY"]',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_placeholder_value(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'api_key = "placeholder"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_test_value(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'secret_key = "changeme"',
        })
        violations = self.rule.evaluate(ctx)
        # changeme is 8 chars — below the 10-char threshold, so no match anyway
        assert len(violations) == 0

    def test_ignores_non_write_tool(self):
        ctx = _ctx("Bash", {
            "command": 'echo "api_key = sk_live_supersecret12345"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_blocks_sensitive_filename(self):
        ctx = _ctx("Write", {
            "file_path": "/app/credentials.json",
            "content": "{}",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1


# ---------------------------------------------------------------------------
# NoEnvCommit
# ---------------------------------------------------------------------------


class TestNoEnvCommit:
    rule = NoEnvCommit()

    def test_blocks_env_file(self):
        ctx = _ctx("Write", {"file_path": ".env", "content": "SECRET=abc"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_env_local(self):
        ctx = _ctx("Write", {"file_path": ".env.local", "content": "X=1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_env_production(self):
        ctx = _ctx("Write", {"file_path": ".env.production", "content": "X=1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_env_example(self):
        ctx = _ctx("Write", {"file_path": ".env.example", "content": "X=1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_env_template(self):
        ctx = _ctx("Write", {"file_path": ".env.template", "content": "X=1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_regular_file(self):
        ctx = _ctx("Write", {"file_path": "config.py", "content": "X=1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# NoForcePush
# ---------------------------------------------------------------------------


class TestNoForcePush:
    rule = NoForcePush()

    def test_blocks_force_push_to_main(self):
        ctx = _ctx("Bash", {"command": "git push --force origin main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_f_flag_to_master(self):
        ctx = _ctx("Bash", {"command": "git push -f origin master"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_regular_push(self):
        ctx = _ctx("Bash", {"command": "git push origin main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_force_push_to_feature_branch(self):
        ctx = _ctx("Bash", {"command": "git push --force origin feature/my-branch"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_bash_tool(self):
        ctx = _ctx("Write", {"file_path": "x.sh", "content": "git push --force origin main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# NoDestructiveCommands
# ---------------------------------------------------------------------------


class TestNoDestructiveCommands:
    rule = NoDestructiveCommands()

    def test_warns_rm_rf(self):
        ctx = _ctx("Bash", {"command": "rm -rf /important/data"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_warns_drop_table(self):
        ctx = _ctx("Bash", {"command": "psql -c 'DROP TABLE users;'"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_warns_git_reset_hard(self):
        ctx = _ctx("Bash", {"command": "git reset --hard HEAD~3"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_warns_git_clean_fd(self):
        ctx = _ctx("Bash", {"command": "git clean -fd"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_safe_commands(self):
        ctx = _ctx("Bash", {"command": "ls -la && echo hello"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_rm_rf_node_modules(self):
        ctx = _ctx("Bash", {"command": "rm -rf node_modules"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_rm_rf_pycache(self):
        ctx = _ctx("Bash", {"command": "rm -rf __pycache__"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_rm_rf_dist(self):
        ctx = _ctx("Bash", {"command": "rm -rf dist"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# DependencyHygiene
# ---------------------------------------------------------------------------


class TestDependencyHygiene:
    rule = DependencyHygiene()

    def test_warns_pip_install(self):
        ctx = _ctx("Bash", {"command": "pip install requests"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "poetry/uv" in violations[0].suggestion

    def test_warns_npm_install_package(self):
        ctx = _ctx("Bash", {"command": "npm install express"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "npm ci" in violations[0].suggestion

    def test_allows_pip_install_editable(self):
        ctx = _ctx("Bash", {"command": "pip install -e ."})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_npm_install_bare(self):
        ctx = _ctx("Bash", {"command": "npm install"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_npm_ci(self):
        ctx = _ctx("Bash", {"command": "npm ci"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_poetry_add(self):
        ctx = _ctx("Bash", {"command": "poetry add requests"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_uv_add(self):
        ctx = _ctx("Bash", {"command": "uv add requests"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# Pack loader
# ---------------------------------------------------------------------------


class TestPackLoader:
    def test_load_universal_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["universal"])
        assert len(rules) == 10
        ids = {r.id for r in rules}
        assert "no-secrets" in ids
        assert "no-env-commit" in ids
        assert "no-force-push" in ids
        assert "no-destructive-commands" in ids
        assert "dependency-hygiene" in ids
        assert "max-file-size" in ids
        assert "drift-detector" in ids
        assert "no-debug-artifacts" in ids
        assert "no-todo-left" in ids
        assert "test-with-changes" in ids

    def test_load_unknown_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["nonexistent"])
        assert rules == []
