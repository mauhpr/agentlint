"""Tests for git checkpoint utilities."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from agentlint.utils.git import git_clean_stashes, git_has_changes, git_stash_push, is_git_repo


class TestIsGitRepo:
    @patch("agentlint.utils.git.subprocess.run")
    def test_returns_true_for_git_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="true\n")
        assert is_git_repo("/tmp/project") is True

    @patch("agentlint.utils.git.subprocess.run")
    def test_returns_false_for_non_git_dir(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="", stderr="fatal")
        assert is_git_repo("/tmp/not-git") is False

    @patch("agentlint.utils.git.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_false_when_git_not_installed(self, mock_run):
        assert is_git_repo("/tmp/project") is False

    @patch("agentlint.utils.git.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5))
    def test_returns_false_on_timeout(self, mock_run):
        assert is_git_repo("/tmp/project") is False


class TestGitHasChanges:
    @patch("agentlint.utils.git.subprocess.run")
    def test_returns_true_with_changes(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=" M file.py\n")
        assert git_has_changes("/tmp/project") is True

    @patch("agentlint.utils.git.subprocess.run")
    def test_returns_false_with_clean_tree(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        assert git_has_changes("/tmp/project") is False

    @patch("agentlint.utils.git.subprocess.run")
    def test_returns_false_on_error(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        assert git_has_changes("/tmp/project") is False

    @patch("agentlint.utils.git.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_false_when_git_not_installed(self, mock_run):
        assert git_has_changes("/tmp/project") is False

    @patch("agentlint.utils.git.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5))
    def test_returns_false_on_timeout(self, mock_run):
        assert git_has_changes("/tmp/project") is False


class TestGitStashPush:
    @patch("agentlint.utils.git.subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="Saved working directory\n")
        assert git_stash_push("/tmp/project", "test-msg") is True
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "stash" in args
        assert "test-msg" in args

    @patch("agentlint.utils.git.subprocess.run")
    def test_returns_false_on_no_changes(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="No local changes to save\n")
        assert git_stash_push("/tmp/project", "test-msg") is False

    @patch("agentlint.utils.git.subprocess.run")
    def test_returns_false_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        assert git_stash_push("/tmp/project", "test-msg") is False

    @patch("agentlint.utils.git.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_false_when_git_not_installed(self, mock_run):
        assert git_stash_push("/tmp/project", "test-msg") is False

    @patch("agentlint.utils.git.subprocess.run", side_effect=subprocess.TimeoutExpired("git", 5))
    def test_returns_false_on_timeout(self, mock_run):
        assert git_stash_push("/tmp/project", "test-msg") is False


class TestGitCleanStashes:
    @patch("agentlint.utils.git.subprocess.run")
    def test_removes_old_stashes(self, mock_run):
        import time

        old_ts = int(time.time()) - 100000  # well over 24h ago

        def run_side_effect(cmd, **kwargs):
            if "stash" in cmd and "list" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout=f"stash@{{0}}: On main: agentlint-checkpoint-123\nstash@{{1}}: On main: unrelated\n",
                )
            if "log" in cmd:
                return MagicMock(returncode=0, stdout=f"{old_ts}\n")
            if "drop" in cmd:
                return MagicMock(returncode=0, stdout="Dropped stash@{0}\n")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = run_side_effect
        result = git_clean_stashes("/tmp/project", "agentlint-checkpoint", 24)
        assert result == 1

    @patch("agentlint.utils.git.subprocess.run")
    def test_keeps_recent_stashes(self, mock_run):
        import time

        recent_ts = int(time.time()) - 100  # just a few minutes ago

        def run_side_effect(cmd, **kwargs):
            if "stash" in cmd and "list" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="stash@{0}: On main: agentlint-checkpoint-123\n",
                )
            if "log" in cmd:
                return MagicMock(returncode=0, stdout=f"{recent_ts}\n")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = run_side_effect
        result = git_clean_stashes("/tmp/project", "agentlint-checkpoint", 24)
        assert result == 0

    @patch("agentlint.utils.git.subprocess.run")
    def test_returns_zero_on_no_matching_stashes(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="stash@{0}: On main: unrelated stash\n",
        )
        result = git_clean_stashes("/tmp/project", "agentlint-checkpoint", 24)
        assert result == 0

    @patch("agentlint.utils.git.subprocess.run")
    def test_returns_zero_on_empty_stash_list(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        result = git_clean_stashes("/tmp/project", "agentlint-checkpoint", 24)
        assert result == 0

    @patch("agentlint.utils.git.subprocess.run")
    def test_returns_zero_on_git_error(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        result = git_clean_stashes("/tmp/project", "agentlint-checkpoint", 24)
        assert result == 0

    @patch("agentlint.utils.git.subprocess.run", side_effect=FileNotFoundError)
    def test_returns_zero_when_git_not_installed(self, mock_run):
        result = git_clean_stashes("/tmp/project", "agentlint-checkpoint", 24)
        assert result == 0

    @patch("agentlint.utils.git.subprocess.run")
    def test_skips_malformed_stash_lines(self, mock_run):
        """Malformed stash line (no index) should be skipped gracefully."""
        def run_side_effect(cmd, **kwargs):
            if "stash" in cmd and "list" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="malformed-line agentlint-checkpoint-123\n",
                )
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = run_side_effect
        result = git_clean_stashes("/tmp/project", "agentlint-checkpoint", 24)
        assert result == 0

    @patch("agentlint.utils.git.subprocess.run")
    def test_skips_stash_when_log_fails(self, mock_run):
        """If git log for a stash timestamp returns non-zero, skip that stash."""

        def run_side_effect(cmd, **kwargs):
            if "stash" in cmd and "list" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="stash@{0}: On main: agentlint-checkpoint-123\n",
                )
            if "log" in cmd:
                return MagicMock(returncode=1, stdout="", stderr="error")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = run_side_effect
        result = git_clean_stashes("/tmp/project", "agentlint-checkpoint", 24)
        assert result == 0

    @patch("agentlint.utils.git.subprocess.run")
    def test_handles_timeout_during_stash_cleanup(self, mock_run):
        """Timeout during per-stash git log should be caught gracefully."""
        call_count = 0

        def run_side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "stash" in cmd and "list" in cmd:
                return MagicMock(
                    returncode=0,
                    stdout="stash@{0}: On main: agentlint-checkpoint-123\n",
                )
            if "log" in cmd:
                raise subprocess.TimeoutExpired("git", 5)
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = run_side_effect
        result = git_clean_stashes("/tmp/project", "agentlint-checkpoint", 24)
        assert result == 0


class TestGitCheckpointIntegration:
    """Integration tests with real git repo."""

    def test_full_checkpoint_workflow(self, tmp_path):
        """Create a real git repo, dirty it, checkpoint, verify stash exists."""
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path), capture_output=True,
        )

        # Create initial commit.
        (tmp_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path), capture_output=True,
        )

        # Dirty the working tree.
        (tmp_path / "file.txt").write_text("modified")

        assert is_git_repo(str(tmp_path)) is True
        assert git_has_changes(str(tmp_path)) is True

        # Create checkpoint.
        result = git_stash_push(str(tmp_path), "agentlint-checkpoint-test")
        assert result is True

        # Verify stash exists.
        stash_list = subprocess.run(
            ["git", "stash", "list"],
            cwd=str(tmp_path), capture_output=True, text=True,
        )
        assert "agentlint-checkpoint-test" in stash_list.stdout

        # File should be back to original.
        assert (tmp_path / "file.txt").read_text() == "hello"

    def test_no_stash_on_clean_tree(self, tmp_path):
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=str(tmp_path), capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=str(tmp_path), capture_output=True,
        )
        (tmp_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=str(tmp_path), capture_output=True,
        )

        assert git_has_changes(str(tmp_path)) is False
        result = git_stash_push(str(tmp_path), "agentlint-checkpoint-test")
        assert result is False

    def test_is_git_repo_on_non_git_dir(self, tmp_path):
        assert is_git_repo(str(tmp_path)) is False
