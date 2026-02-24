"""End-to-end integration tests for AgentLint."""
import json
import os
import subprocess
import sys

class TestEndToEnd:
    def _run_agentlint(self, args: list[str], stdin_data: dict | None = None, project_dir: str = "/tmp", env: dict | None = None):
        cmd = [sys.executable, "-m", "agentlint.cli"] + args + ["--project-dir", project_dir]
        input_data = json.dumps(stdin_data) if stdin_data else "{}"
        run_env = {**os.environ, **(env or {})}
        result = subprocess.run(
            cmd, input=input_data, capture_output=True, text=True, timeout=10, env=run_env,
        )
        return result

    def test_blocks_secrets_end_to_end(self, tmp_path):
        """Secrets in Write content should be blocked via deny protocol."""
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
        assert result.returncode == 0  # deny protocol uses exit 0
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "no-secrets" in output["hookSpecificOutput"]["permissionDecisionReason"]

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
        """Force push to main should be blocked via deny protocol."""
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Bash",
                "tool_input": {"command": "git push --force origin main"},
            },
            project_dir=str(tmp_path),
        )
        assert result.returncode == 0  # deny protocol uses exit 0
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "no-force-push" in output["hookSpecificOutput"]["permissionDecisionReason"]

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
        """Writing .env should be blocked via deny protocol."""
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
        assert result.returncode == 0  # deny protocol uses exit 0
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_init_and_check_flow(self, tmp_path):
        """Init should create config, then check should work with it."""
        # Run init
        init_result = self._run_agentlint(["init"], project_dir=str(tmp_path))
        assert init_result.returncode == 0
        assert (tmp_path / "agentlint.yml").exists()

        config_content = (tmp_path / "agentlint.yml").read_text()
        assert "universal" in config_content

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
        """In strict mode, warnings become errors and use deny protocol."""
        (tmp_path / "agentlint.yml").write_text("severity: strict\npacks:\n  - universal\n")
        result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Bash",
                "tool_input": {"command": "pip install requests"},
            },
            project_dir=str(tmp_path),
        )
        # In strict mode, dependency-hygiene WARNING becomes ERROR → deny protocol
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_report_command(self, tmp_path):
        """Report command should output session summary."""
        result = self._run_agentlint(["report"], project_dir=str(tmp_path))
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "AgentLint Session Report" in output["systemMessage"]

    def test_circuit_breaker_degrades_after_threshold(self, tmp_path):
        """After 3 identical blocks from same rule, should degrade to warning."""
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        cache_dir = str(tmp_path / "cb_cache")
        env = {
            "CLAUDE_SESSION_ID": "test-cb-e2e",
            "AGENTLINT_CACHE_DIR": cache_dir,
        }

        for i in range(3):
            result = self._run_agentlint(
                ["check", "--event", "PreToolUse"],
                stdin_data={
                    "tool_name": "Bash",
                    "tool_input": {"command": "git push --force origin main"},
                },
                project_dir=str(tmp_path),
                env=env,
            )
            assert result.returncode == 0
            output = json.loads(result.stdout)

            if i < 2:
                # First 2 fires should block (deny protocol)
                assert "hookSpecificOutput" in output, f"Fire {i+1} should block"
                assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
            else:
                # 3rd fire should be degraded to warning (systemMessage, not deny)
                assert "systemMessage" in output, f"Fire {i+1} should be degraded to warning"
                assert "hookSpecificOutput" not in output

    def test_circuit_breaker_never_degrades_secrets(self, tmp_path):
        """no-secrets should never be degraded by circuit breaker."""
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        cache_dir = str(tmp_path / "cb_secrets_cache")
        env = {
            "CLAUDE_SESSION_ID": "test-cb-secrets",
            "AGENTLINT_CACHE_DIR": cache_dir,
        }

        for i in range(5):
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
                env=env,
            )
            assert result.returncode == 0
            output = json.loads(result.stdout)
            # Should ALWAYS block — never degraded
            assert "hookSpecificOutput" in output, f"Fire {i+1}: no-secrets should always block"
            assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
