"""Tests for the agentlint ci command."""
from __future__ import annotations

import json
import subprocess
import sys

from click.testing import CliRunner

from agentlint.cli import main


class TestCiCommand:
    def _run_ci(self, tmp_path, args=None, files=None, config=None):
        """Helper to set up a git repo with files and run ci."""
        # Create agentlint.yml
        (tmp_path / "agentlint.yml").write_text(config or "packs:\n  - universal\n")

        # Init git repo and commit files
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)

        if files:
            for name, content in files.items():
                path = tmp_path / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content)

        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        runner = CliRunner()
        cmd_args = ["ci", "--project-dir", str(tmp_path)]
        if args:
            cmd_args.extend(args)
        return runner.invoke(main, cmd_args)

    def test_ci_no_changes_exits_zero(self, tmp_path):
        result = self._run_ci(tmp_path, files={"app.py": "x = 1\n"})
        assert result.exit_code == 0
        assert "No changed files" in result.output or "Clean" in result.output

    def test_ci_clean_files_exits_zero(self, tmp_path):
        """Uncommitted clean file should pass."""
        # Commit initial, then add a clean file
        self._run_ci(tmp_path, files={"app.py": "x = 1\n"})
        (tmp_path / "clean.py").write_text("def hello():\n    return 'world'\n")
        runner = CliRunner()
        result = runner.invoke(main, ["ci", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0

    def test_ci_secret_detected_exits_one(self, tmp_path):
        """File with a secret should cause exit 1."""
        self._run_ci(tmp_path, files={"init.py": "x = 1\n"})
        (tmp_path / "bad.py").write_text('API_KEY = "sk_live_abc123def456ghi789"\n')
        runner = CliRunner()
        result = runner.invoke(main, ["ci", "--project-dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "no-secrets" in result.output

    def test_ci_warning_exits_zero(self, tmp_path):
        """Warnings should not fail CI (exit 0)."""
        self._run_ci(tmp_path, files={"init.py": "x = 1\n"})
        # Large file triggers max-file-size warning but not error
        (tmp_path / "big.py").write_text("x = 1\n" * 600)
        runner = CliRunner()
        result = runner.invoke(main, ["ci", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0

    def test_ci_text_format(self, tmp_path):
        """Text format should show human-readable output."""
        self._run_ci(tmp_path, files={"init.py": "x = 1\n"})
        (tmp_path / "bad.py").write_text('SECRET = "sk_live_test000000000000"\n')
        runner = CliRunner()
        result = runner.invoke(main, ["ci", "--project-dir", str(tmp_path)])
        assert "ERROR" in result.output
        assert "violation" in result.output

    def test_ci_json_format(self, tmp_path):
        """JSON format should produce valid JSON."""
        self._run_ci(tmp_path, files={"init.py": "x = 1\n"})
        (tmp_path / "bad.py").write_text('TOKEN = "sk_live_test000000000000"\n')
        runner = CliRunner()
        result = runner.invoke(main, ["ci", "--format", "json", "--project-dir", str(tmp_path)])
        parsed = json.loads(result.output)
        assert "violations" in parsed
        assert "files_scanned" in parsed
        assert parsed["files_scanned"] >= 1

    def test_ci_respects_config(self, tmp_path):
        """CI should respect agentlint.yml rules config."""
        self._run_ci(
            tmp_path,
            files={"init.py": "x = 1\n"},
            config="packs:\n  - universal\nrules:\n  no-secrets:\n    enabled: false\n",
        )
        (tmp_path / "bad.py").write_text('SECRET = "sk_live_test000000000000"\n')
        runner = CliRunner()
        result = runner.invoke(main, ["ci", "--project-dir", str(tmp_path)])
        # no-secrets is disabled, so should pass
        assert result.exit_code == 0

    def test_ci_skips_binary_files(self, tmp_path):
        """Binary files should be skipped without false positives."""
        self._run_ci(tmp_path, files={"init.py": "x = 1\n"})
        (tmp_path / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
        runner = CliRunner()
        result = runner.invoke(main, ["ci", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0

    def test_ci_json_no_changes(self, tmp_path):
        """JSON format with no changes should return empty violations."""
        result = self._run_ci(tmp_path, args=["--format", "json"], files={"app.py": "x = 1\n"})
        parsed = json.loads(result.output)
        assert parsed["violations"] == []
        assert parsed["files_scanned"] == 0

    def test_ci_clean_summary_text(self, tmp_path):
        """Clean scan should show summary message."""
        self._run_ci(tmp_path, files={"init.py": "x = 1\n"})
        (tmp_path / "clean.py").write_text("x = 1\n")
        runner = CliRunner()
        result = runner.invoke(main, ["ci", "--project-dir", str(tmp_path)])
        assert "Clean" in result.output or "No changed" in result.output


class TestGetDiffFiles:
    def test_diff_range_returns_files(self, tmp_path):
        from agentlint.utils.git import get_diff_files
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
        (tmp_path / "a.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "first"], cwd=tmp_path, capture_output=True)
        (tmp_path / "b.py").write_text("y = 2\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], cwd=tmp_path, capture_output=True)
        files = get_diff_files(str(tmp_path), "HEAD~1...HEAD")
        assert any("b.py" in f for f in files)

    def test_diff_range_invalid_returns_empty(self, tmp_path):
        from agentlint.utils.git import get_diff_files
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
        (tmp_path / "a.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "first"], cwd=tmp_path, capture_output=True)
        files = get_diff_files(str(tmp_path), "nonexistent...alsonotreal")
        assert files == []

    def test_diff_no_range_falls_back(self, tmp_path):
        from agentlint.utils.git import get_diff_files
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, capture_output=True)
        (tmp_path / "a.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "first"], cwd=tmp_path, capture_output=True)
        (tmp_path / "new.py").write_text("y = 2\n")
        files = get_diff_files(str(tmp_path), None)
        assert any("new.py" in f for f in files)


class TestCiEndToEnd:
    def _run_agentlint(self, args, project_dir, env=None):
        import os
        cmd = [sys.executable, "-m", "agentlint.cli"] + args + ["--project-dir", project_dir]
        run_env = {**os.environ, **(env or {})}
        return subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=run_env)

    def test_ci_end_to_end(self, tmp_path):
        """Full E2E: init repo, commit secret, run agentlint ci."""
        subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, capture_output=True)
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        (tmp_path / "ok.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, capture_output=True)

        # Add a file with a secret (uncommitted)
        (tmp_path / "leaked.py").write_text('DB_PASSWORD = "sk_live_reallyBadSecret123"\n')

        result = self._run_agentlint(["ci"], str(tmp_path))
        assert result.returncode == 1
        assert "no-secrets" in result.stdout
