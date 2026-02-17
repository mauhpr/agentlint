"""Tests for git utilities."""
from __future__ import annotations

import subprocess

from agentlint.utils.git import get_changed_files


class TestGetChangedFiles:
    def test_returns_empty_for_non_git_dir(self, tmp_path):
        result = get_changed_files(str(tmp_path))
        assert result == []

    def test_returns_changed_files_in_git_repo(self, tmp_path):
        # Initialize a git repo with a commit
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)

        # Create and commit a file
        (tmp_path / "file.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=str(tmp_path), capture_output=True)

        # Modify the file (unstaged change)
        (tmp_path / "file.py").write_text("x = 2\n")

        result = get_changed_files(str(tmp_path))
        assert any("file.py" in f for f in result)

    def test_returns_empty_for_clean_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), capture_output=True)

        (tmp_path / "file.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=str(tmp_path), capture_output=True)

        result = get_changed_files(str(tmp_path))
        assert result == []
