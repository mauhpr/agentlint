"""Tests for the git-checkpoint rule."""
from __future__ import annotations

from unittest.mock import patch

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.universal.git_checkpoint import GitCheckpoint


def _ctx(command: str, config: dict | None = None, event: HookEvent = HookEvent.PRE_TOOL_USE) -> RuleContext:
    return RuleContext(
        event=event,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
        config=config or {},
    )


def _stop_ctx(config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.STOP,
        tool_name="",
        tool_input={},
        project_dir="/tmp/project",
        config=config or {},
    )


class TestGitCheckpointRule:
    rule = GitCheckpoint()

    def test_rule_metadata(self):
        assert self.rule.id == "git-checkpoint"
        assert self.rule.pack == "universal"
        assert self.rule.severity == Severity.INFO
        assert HookEvent.PRE_TOOL_USE in self.rule.events
        assert HookEvent.STOP in self.rule.events

    @patch("agentlint.utils.git.git_stash_push", return_value=True)
    @patch("agentlint.utils.git.git_has_changes", return_value=True)
    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    def test_creates_checkpoint_on_rm_rf(self, mock_repo, mock_changes, mock_stash):
        ctx = _ctx("rm -rf ./src")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "checkpoint" in violations[0].message.lower()
        mock_stash.assert_called_once()

    @patch("agentlint.utils.git.git_stash_push", return_value=True)
    @patch("agentlint.utils.git.git_has_changes", return_value=True)
    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    def test_creates_checkpoint_on_git_reset_hard(self, mock_repo, mock_changes, mock_stash):
        ctx = _ctx("git reset --hard HEAD~3")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "checkpoint" in violations[0].message.lower()

    @patch("agentlint.utils.git.git_stash_push", return_value=True)
    @patch("agentlint.utils.git.git_has_changes", return_value=True)
    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    def test_creates_checkpoint_on_git_checkout_dot(self, mock_repo, mock_changes, mock_stash):
        ctx = _ctx("git checkout .")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    @patch("agentlint.utils.git.git_stash_push", return_value=True)
    @patch("agentlint.utils.git.git_has_changes", return_value=True)
    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    def test_creates_checkpoint_on_git_clean(self, mock_repo, mock_changes, mock_stash):
        ctx = _ctx("git clean -fd")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    @patch("agentlint.utils.git.git_stash_push", return_value=True)
    @patch("agentlint.utils.git.git_has_changes", return_value=True)
    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    def test_creates_checkpoint_on_drop_table(self, mock_repo, mock_changes, mock_stash):
        ctx = _ctx("psql -c 'DROP TABLE users;'")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_skips_non_bash_tool(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "x.py", "content": "rm -rf /"},
            project_dir="/tmp/project",
            config={},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_empty_command(self):
        ctx = _ctx("")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    @patch("agentlint.utils.git.is_git_repo", return_value=False)
    def test_skips_non_git_repo(self, mock_repo):
        ctx = _ctx("rm -rf .")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    @patch("agentlint.utils.git.git_has_changes", return_value=False)
    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    def test_skips_clean_working_tree(self, mock_repo, mock_changes):
        ctx = _ctx("rm -rf .")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    @patch("agentlint.utils.git.git_stash_push", return_value=False)
    @patch("agentlint.utils.git.git_has_changes", return_value=True)
    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    def test_no_violation_when_stash_fails(self, mock_repo, mock_changes, mock_stash):
        ctx = _ctx("rm -rf .")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_safe_command(self):
        ctx = _ctx("ls -la")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


class TestGitCheckpointConfig:
    rule = GitCheckpoint()

    @patch("agentlint.utils.git.git_stash_push", return_value=True)
    @patch("agentlint.utils.git.git_has_changes", return_value=True)
    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    def test_custom_trigger_pattern(self, mock_repo, mock_changes, mock_stash):
        config = {"git-checkpoint": {"triggers": [r"\bmy-dangerous-cmd\b"]}}
        ctx = _ctx("my-dangerous-cmd --force", config=config)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    @patch("agentlint.utils.git.git_has_changes", return_value=True)
    def test_custom_trigger_overrides_defaults(self, mock_changes, mock_repo):
        config = {"git-checkpoint": {"triggers": [r"\bmy-cmd\b"]}}
        ctx = _ctx("rm -rf .", config=config)
        violations = self.rule.evaluate(ctx)
        # rm -rf should NOT trigger because custom triggers override defaults.
        assert len(violations) == 0


class TestGitCheckpointCleanup:
    rule = GitCheckpoint()

    @patch("agentlint.utils.git.git_clean_stashes", return_value=3)
    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    def test_cleanup_on_stop(self, mock_repo, mock_clean):
        ctx = _stop_ctx()
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "3" in violations[0].message
        assert "Cleaned up" in violations[0].message

    @patch("agentlint.utils.git.git_clean_stashes", return_value=0)
    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    def test_no_violation_when_nothing_to_clean(self, mock_repo, mock_clean):
        ctx = _stop_ctx()
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    @patch("agentlint.utils.git.is_git_repo", return_value=False)
    def test_cleanup_skips_non_git(self, mock_repo):
        ctx = _stop_ctx()
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    @patch("agentlint.utils.git.git_clean_stashes", return_value=2)
    @patch("agentlint.utils.git.is_git_repo", return_value=True)
    def test_custom_cleanup_hours(self, mock_repo, mock_clean):
        config = {"git-checkpoint": {"cleanup_hours": 48}}
        ctx = _stop_ctx(config=config)
        violations = self.rule.evaluate(ctx)
        mock_clean.assert_called_once_with("/tmp/project", "agentlint-checkpoint", 48)


class TestGitCheckpointDisabledByDefault:
    """Verify that git-checkpoint is disabled unless explicitly enabled."""

    def test_disabled_in_default_config(self):
        from agentlint.config import AgentLintConfig

        config = AgentLintConfig()
        assert not config.is_rule_enabled("git-checkpoint")

    def test_enabled_when_configured(self):
        from agentlint.config import AgentLintConfig

        config = AgentLintConfig(rules={"git-checkpoint": {"enabled": True}})
        assert config.is_rule_enabled("git-checkpoint")

    def test_other_rules_still_enabled_by_default(self):
        from agentlint.config import AgentLintConfig

        config = AgentLintConfig()
        assert config.is_rule_enabled("no-secrets")
        assert config.is_rule_enabled("no-destructive-commands")
