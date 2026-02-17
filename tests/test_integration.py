"""End-to-end integration tests for AgentLint."""
import json
import subprocess
import sys

class TestEndToEnd:
    def _run_agentlint(self, args: list[str], stdin_data: dict | None = None, project_dir: str = "/tmp"):
        cmd = [sys.executable, "-m", "agentlint.cli"] + args + ["--project-dir", project_dir]
        input_data = json.dumps(stdin_data) if stdin_data else "{}"
        result = subprocess.run(
            cmd, input=input_data, capture_output=True, text=True, timeout=10
        )
        return result

    def test_blocks_secrets_end_to_end(self, tmp_path):
        """Secrets in Write content should be blocked (exit 2)."""
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "/tmp/config.py",
                    "content": 'SECRET = "sk_live_TESTKEY000000"',
                },
            },
            project_dir=str(tmp_path),
        )
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert "no-secrets" in output["systemMessage"]

    def test_allows_clean_code_end_to_end(self, tmp_path):
        """Clean code should pass (exit 0)."""
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "/tmp/app.py",
                    "content": "def add(a: int, b: int) -> int:\n    return a + b\n",
                },
            },
            project_dir=str(tmp_path),
        )
        assert result.returncode == 0

    def test_blocks_force_push_end_to_end(self, tmp_path):
        """Force push to main should be blocked."""
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Bash",
                "tool_input": {"command": "git push --force origin main"},
            },
            project_dir=str(tmp_path),
        )
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert "no-force-push" in output["systemMessage"]

    def test_warns_pip_install_end_to_end(self, tmp_path):
        """pip install should warn but not block (exit 0)."""
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Bash",
                "tool_input": {"command": "pip install requests"},
            },
            project_dir=str(tmp_path),
        )
        assert result.returncode == 0  # warning, not blocking
        output = json.loads(result.stdout)
        assert "dependency-hygiene" in output["systemMessage"]

    def test_blocks_env_file_write(self, tmp_path):
        """Writing .env should be blocked."""
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Write",
                "tool_input": {
                    "file_path": str(tmp_path / ".env"),
                    "content": "SECRET_KEY=abc123",
                },
            },
            project_dir=str(tmp_path),
        )
        assert result.returncode == 2

    def test_init_and_check_flow(self, tmp_path):
        """Init should create config, then check should work with it."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        # Run init
        init_result = self._run_agentlint(["init"], project_dir=str(tmp_path))
        assert init_result.returncode == 0
        assert (tmp_path / "agentlint.yml").exists()

        config_content = (tmp_path / "agentlint.yml").read_text()
        assert "python" in config_content

        # Run check with the generated config
        check_result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Bash",
                "tool_input": {"command": "pip install requests"},
            },
            project_dir=str(tmp_path),
        )
        assert check_result.returncode == 0  # warning, not error
        output = json.loads(check_result.stdout)
        assert "dependency-hygiene" in output["systemMessage"]

    def test_strict_mode_blocks_warnings(self, tmp_path):
        """In strict mode, warnings become errors."""
        (tmp_path / "agentlint.yml").write_text("severity: strict\npacks:\n  - universal\n")
        result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Bash",
                "tool_input": {"command": "pip install requests"},
            },
            project_dir=str(tmp_path),
        )
        # In strict mode, dependency-hygiene WARNING becomes ERROR
        assert result.returncode == 2

    def test_report_command(self, tmp_path):
        """Report command should output session summary."""
        result = self._run_agentlint(["report"], project_dir=str(tmp_path))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "AgentLint Session Report" in output["systemMessage"]
