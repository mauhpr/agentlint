"""Tests for session state persistence."""
from __future__ import annotations

from agentlint.session import cleanup_session, load_session, save_session, _session_path


class TestSessionPersistence:
    def test_load_returns_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "test-session-1")
        assert load_session() == {}

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "test-session-2")

        state = {"files_edited": 5, "last_test_run": False}
        save_session(state)

        loaded = load_session()
        assert loaded == state

    def test_save_creates_directory(self, tmp_path, monkeypatch):
        cache_dir = tmp_path / "deep" / "nested"
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(cache_dir))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "test-session-3")

        save_session({"key": "value"})
        assert cache_dir.exists()
        assert load_session() == {"key": "value"}

    def test_cleanup_removes_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "test-session-4")

        save_session({"data": True})
        path = _session_path()
        assert path.exists()

        cleanup_session()
        assert not path.exists()

    def test_cleanup_noop_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "nonexistent")
        cleanup_session()  # Should not raise

    def test_load_handles_corrupt_json(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "test-corrupt")

        path = _session_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not valid json {{{", encoding="utf-8")

        assert load_session() == {}

    def test_explicit_key_overrides_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "env-session")

        save_session({"source": "explicit"}, key="explicit-key")
        loaded = load_session(key="explicit-key")
        assert loaded == {"source": "explicit"}

    def test_fallback_to_ppid_when_no_session_id(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path))
        monkeypatch.delenv("CLAUDE_SESSION_ID", raising=False)

        save_session({"ppid": True})
        loaded = load_session()
        assert loaded == {"ppid": True}

    def test_session_state_mutation_persists(self, tmp_path, monkeypatch):
        """Simulate the real flow: load, mutate, save, reload."""
        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "mutation-test")

        # First invocation: load empty, mutate, save
        state = load_session()
        state["files_edited"] = 3
        save_session(state)

        # Second invocation: load, mutate, save
        state2 = load_session()
        assert state2["files_edited"] == 3
        state2["files_edited"] = 7
        save_session(state2)

        # Third invocation: verify
        state3 = load_session()
        assert state3["files_edited"] == 7
