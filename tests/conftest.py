from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_agentchute_credentials(monkeypatch, tmp_path):
    """Keep tests from reading or writing the developer's real AgentChute login."""
    monkeypatch.setenv(
        "AGENTLINT_AGENTCHUTE_CREDENTIALS_FILE",
        str(tmp_path / "agentchute.json"),
    )
