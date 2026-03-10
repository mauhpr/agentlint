"""Tests for session recording."""
from __future__ import annotations

import time

from agentlint.config import AgentLintConfig
from agentlint.recorder import (
    append_event,
    clear_recordings,
    is_recording_enabled,
    list_recordings,
    load_recording,
    recording_stats,
    summarize_tool_input,
)


class TestSummarizeToolInput:
    def test_bash_truncates_command(self):
        long_cmd = "x" * 500
        result = summarize_tool_input("Bash", {"command": long_cmd})
        assert result["command"] == "x" * 200
        assert result["file_path"] is None

    def test_write_omits_content(self):
        result = summarize_tool_input("Write", {
            "file_path": "/foo/bar.py",
            "content": "a" * 1000,
        })
        assert result["file_path"] == "/foo/bar.py"
        assert result["content_length"] == 1000
        assert "a" * 1000 not in str(result)

    def test_edit_uses_new_string_length(self):
        result = summarize_tool_input("Edit", {
            "file_path": "/f.py",
            "old_string": "old",
            "new_string": "new content here",
        })
        assert result["file_path"] == "/f.py"
        assert result["content_length"] == len("new content here")
        assert result["old_content_length"] == len("old")

    def test_prompt_truncates(self):
        long_prompt = "p" * 300
        result = summarize_tool_input("UserPromptSubmit", {}, prompt=long_prompt)
        assert result.get("prompt_preview") == "p" * 100

    def test_read_captures_file_path(self):
        result = summarize_tool_input("Read", {"file_path": "/a/b.py"})
        assert result["file_path"] == "/a/b.py"

    def test_grep_captures_pattern(self):
        result = summarize_tool_input("Grep", {"pattern": "TODO"})
        assert result["file_path"] == "TODO"

    def test_agent_captures_subagent_type_and_description(self):
        result = summarize_tool_input("Agent", {
            "subagent_type": "Explore",
            "description": "Find auth middleware",
        })
        assert result["subagent_type"] == "Explore"
        assert result["description"] == "Find auth middleware"

    def test_agent_truncates_long_description(self):
        result = summarize_tool_input("Task", {
            "description": "d" * 300,
        })
        assert result["description"] == "d" * 100

    def test_webfetch_captures_url(self):
        result = summarize_tool_input("WebFetch", {
            "url": "https://example.com/api/docs",
        })
        assert result["url"] == "https://example.com/api/docs"

    def test_webfetch_truncates_long_url(self):
        long_url = "https://example.com/" + "a" * 300
        result = summarize_tool_input("WebFetch", {"url": long_url})
        assert len(result["url"]) == 200

    def test_websearch_captures_query(self):
        result = summarize_tool_input("WebSearch", {"query": "python asyncio tutorial"})
        assert result["query"] == "python asyncio tutorial"

    def test_notebook_edit_captures_cell(self):
        result = summarize_tool_input("NotebookEdit", {
            "file_path": "/nb.ipynb",
            "cell_number": 3,
        })
        assert result["file_path"] == "/nb.ipynb"
        assert result["cell_index"] == 3

    def test_unknown_tool_returns_empty_summary(self):
        result = summarize_tool_input("SomeNewTool", {"data": "value"})
        assert result["command"] is None
        assert result["file_path"] is None
        assert result["content_length"] is None


class TestAppendAndLoad:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        entry1 = {"ts": 1.0, "event": "PreToolUse", "tool_name": "Bash"}
        entry2 = {"ts": 2.0, "event": "PostToolUse", "tool_name": "Bash"}

        append_event(entry1, "sess-1")
        append_event(entry2, "sess-1")

        loaded = load_recording("sess-1")
        assert len(loaded) == 2
        assert loaded[0]["ts"] == 1.0
        assert loaded[1]["event"] == "PostToolUse"

    def test_load_missing_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        assert load_recording("nonexistent") == []

    def test_creates_directory(self, tmp_path, monkeypatch):
        deep = tmp_path / "a" / "b"
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(deep))
        append_event({"ts": 1.0}, "s1")
        assert deep.exists()
        assert load_recording("s1") == [{"ts": 1.0}]

    def test_key_sanitization_special_chars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        # Keys with colons, pipes, and other unsafe chars should be sanitized
        append_event({"ts": 1.0}, "sess:with|special*chars?")
        # File should exist with sanitized name
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1
        assert ":" not in files[0].name
        assert "|" not in files[0].name
        assert "*" not in files[0].name
        assert "?" not in files[0].name

    def test_corrupt_lines_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        path = tmp_path / "bad.jsonl"
        path.write_text('{"ok":1}\nnot json\n{"ok":2}\n')
        loaded = load_recording("bad")
        assert len(loaded) == 2
        assert loaded[0] == {"ok": 1}


class TestListRecordings:
    def test_lists_multiple_sessions(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        append_event({"ts": 1.0}, "alpha")
        append_event({"ts": 2.0}, "alpha")
        append_event({"ts": 3.0}, "beta")

        recs = list_recordings()
        assert len(recs) == 2
        keys = {r["session_key"] for r in recs}
        assert keys == {"alpha", "beta"}

        alpha = next(r for r in recs if r["session_key"] == "alpha")
        assert alpha["event_count"] == 2

    def test_empty_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        assert list_recordings() == []

    def test_nonexistent_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path / "nope"))
        assert list_recordings() == []


class TestRecordingStats:
    def test_aggregation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        for i in range(3):
            append_event({
                "ts": float(i), "event": "PreToolUse",
                "tool_name": "Bash", "violations": [],
            }, "s1")
        append_event({
            "ts": 10.0, "event": "PreToolUse",
            "tool_name": "Write",
            "violations": [{"rule_id": "no-secrets", "severity": "error"}],
        }, "s1")

        stats = recording_stats()
        assert stats["total_events"] == 4
        assert stats["sessions"] == 1
        assert stats["top_tools"][0] == ("Bash", 3)
        assert ("no-secrets", 1) in stats["top_rules"]

    def test_filter_by_keys(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        append_event({"ts": 1.0, "event": "PreToolUse", "tool_name": "Bash"}, "keep")
        append_event({"ts": 2.0, "event": "PreToolUse", "tool_name": "Read"}, "skip")

        stats = recording_stats(keys=["keep"])
        assert stats["total_events"] == 1
        assert stats["sessions"] == 1


class TestClearRecordings:
    def test_clear_all(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        append_event({"ts": 1.0}, "a")
        append_event({"ts": 2.0}, "b")

        removed = clear_recordings(older_than_days=0)
        assert removed == 2
        assert list_recordings() == []

    def test_clear_older_than(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path))
        append_event({"ts": 1.0}, "recent")

        # Artificially age one file
        import os
        old_path = tmp_path / "old.jsonl"
        old_path.write_text('{"ts":0}\n')
        old_time = time.time() - 86400 * 10  # 10 days ago
        os.utime(old_path, (old_time, old_time))

        removed = clear_recordings(older_than_days=5)
        assert removed == 1
        remaining = list_recordings()
        assert len(remaining) == 1
        assert remaining[0]["session_key"] == "recent"

    def test_clear_nonexistent_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDINGS_DIR", str(tmp_path / "nope"))
        assert clear_recordings() == 0


class TestIsRecordingEnabled:
    def test_disabled_by_default(self):
        config = AgentLintConfig()
        assert not is_recording_enabled(config)

    def test_enabled_via_config(self):
        config = AgentLintConfig(recording={"enabled": True})
        assert is_recording_enabled(config)

    def test_env_var_override(self, monkeypatch):
        monkeypatch.setenv("AGENTLINT_RECORDING", "1")
        config = AgentLintConfig()
        assert is_recording_enabled(config)

    def test_env_var_not_set(self, monkeypatch):
        monkeypatch.delenv("AGENTLINT_RECORDING", raising=False)
        config = AgentLintConfig()
        assert not is_recording_enabled(config)
