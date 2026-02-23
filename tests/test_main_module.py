"""Tests for python -m agentlint entry point."""
from __future__ import annotations

import subprocess
import sys


class TestMainModule:
    def test_module_imports_main(self) -> None:
        """__main__.py should import the cli main function."""
        import agentlint.__main__ as m

        assert hasattr(m, "main")
        assert callable(m.main)

    def test_python_m_agentlint_help(self) -> None:
        """python -m agentlint --help should exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "agentlint", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "Usage" in result.stdout

    def test_python_m_agentlint_list_rules(self) -> None:
        """python -m agentlint list-rules should exit 0."""
        result = subprocess.run(
            [sys.executable, "-m", "agentlint", "list-rules"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "no-secrets" in result.stdout
