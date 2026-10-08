from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_agentlint_state(monkeypatch, tmp_path):
    """Keep tests independent from the developer's AgentLint state and login."""
    for platform in ("CODEX", "CLAUDE", "CURSOR", "KIMI", "GROK", "GEMINI", "CONTINUE"):
        monkeypatch.delenv(f"{platform}_PROJECT_DIR", raising=False)
        monkeypatch.delenv(f"{platform}_SESSION_ID", raising=False)
    for name in (
        "OPENAI_RUN_ID",
        "OPENAI_THREAD_ID",
        "OPENAI_SESSION_ID",
        "MCP_SESSION_ID",
        "AGENTLINT_PROJECT_DIR",
        "AGENTLINT_SESSION_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("AGENTLINT_HEARTBEAT_DIR", str(tmp_path / "heartbeat"))
    # User-scope hook files (~/.codex/hooks.json etc.) must not leak in from the
    # developer's machine now that status inspects both scopes.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path / "recordings"))
    monkeypatch.setenv("AGENTLINT_SHELL_PROFILE", str(tmp_path / "shell-profile"))
    monkeypatch.setenv(
        "AGENTLINT_AGENTCHUTE_QUEUE_DIR",
        str(tmp_path / "agentchute-queue"),
    )
    monkeypatch.setenv(
        "AGENTLINT_AGENTCHUTE_POLICY_DIR",
        str(tmp_path / "agentchute-policy"),
    )
    monkeypatch.setenv(
        "AGENTLINT_AGENTCHUTE_CREDENTIALS_FILE",
        str(tmp_path / "agentchute.json"),
    )
    monkeypatch.delenv("AGENTCHUTE_API_URL", raising=False)
    monkeypatch.delenv("AGENTCHUTE_ENABLED", raising=False)
    monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)
    monkeypatch.delenv("AGENTLINT_RECORDING", raising=False)
    monkeypatch.delenv("AGENTLINT_WORKSPACE_CONFIG", raising=False)
