"""Tests for no-leaked-secret-pattern (Phase 19, security pack).

Hybrid rule running cloud-curated gitleaks regexes against Edit/Write
content.

Verifies:
  1. Self-degrading: no license OR empty feed → no violations.
  2. Pattern matching fires for content that hits a regex; redacts the
     match in the message.
  3. Skips invalid regexes silently (one bad upstream pattern doesn't
     break the rule for everyone else).
  4. Caps violations per file at the documented max.
  5. Severity downgrade for non-CRITICAL/HIGH cloud severities.
"""

from __future__ import annotations

from unittest.mock import patch

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.security.no_leaked_secret_pattern import (
    NoLeakedSecretPattern,
    _MAX_VIOLATIONS_PER_FILE,
    _compile,
    _compiled_cache,
)


def _ctx(content: str, *, tool: str = "Write") -> RuleContext:
    tool_input: dict = {"file_path": "/tmp/x.py"}
    if tool == "Edit":
        tool_input["new_string"] = content
    else:
        tool_input["content"] = content
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool,
        tool_input=tool_input,
        project_dir="/tmp/p",
        config={},
    )


# ---------- _compile cache ----------


def setup_module():
    """Clear the compile cache between modules so test ordering doesn't
    matter."""
    _compiled_cache.clear()


def test_compile_caches():
    pat1 = _compile(r"^foo$", "rule-a")
    pat2 = _compile(r"^foo$", "rule-a")
    assert pat1 is pat2  # same object — cached


def test_compile_invalid_returns_none():
    assert _compile(r"(?P<bad>", "rule-bad") is None


# ---------- self-degrading ----------


class TestSelfDegrading:
    rule = NoLeakedSecretPattern()

    def test_no_license_key(self, monkeypatch):
        monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)
        ctx = _ctx("AKIAFAKEXAMPLEKEY1234")
        assert self.rule.evaluate(ctx) == []

    def test_empty_feed(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with patch("agentlint.agentchute.cloud_feed.get",
                   return_value={"patterns": []}):
            assert self.rule.evaluate(_ctx("AKIAFAKEXAMPLEKEY1234")) == []

    def test_non_file_tool(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "AKIAFAKE"},
            project_dir="/tmp",
            config={},
        )
        assert self.rule.evaluate(ctx) == []

    def test_empty_content(self):
        assert self.rule.evaluate(_ctx("")) == []


# ---------- happy path ----------


class TestHappyPath:
    rule = NoLeakedSecretPattern()

    def _feed(self, *patterns):
        return {"patterns": list(patterns)}

    def _patch(self, feed):
        return patch("agentlint.agentchute.cloud_feed.get", return_value=feed)

    def test_fires_on_aws_pattern(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "id": "aws-access-token",
            "title": "AWS access token",
            "regex": r"AKIA[0-9A-Z]{16}",
            "severity": "CRITICAL",
            "tags": ["aws"],
        })
        with self._patch(feed):
            v = self.rule.evaluate(_ctx(
                "AWS_KEY = 'AKIA1234567890ABCDEF'"
            ))
        assert len(v) == 1
        assert v[0].rule_id == "no-leaked-secret-pattern"
        assert "aws-access-token" in v[0].message
        # Match must be redacted in the message
        assert "AKIA1234567890ABCDEF" not in v[0].message
        assert v[0].severity.value == "error"

    def test_redaction_short_match(self, monkeypatch):
        # Short matches (≤8 chars) become *** rather than partial reveal
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "id": "tiny",
            "title": "tiny secret",
            "regex": r"sk-\d+",
            "severity": "HIGH",
        })
        with self._patch(feed):
            v = self.rule.evaluate(_ctx("token = 'sk-123'"))
        assert len(v) == 1
        assert "***" in v[0].message
        assert "sk-123" not in v[0].message

    def test_severity_downgrade_for_low_severity_pattern(self, monkeypatch):
        # MEDIUM severity from feed maps to WARNING (not ERROR)
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "id": "obscure",
            "title": "obscure pattern",
            "regex": r"obscure-[a-z]+",
            "severity": "MEDIUM",
        })
        with self._patch(feed):
            v = self.rule.evaluate(_ctx("x = obscure-thing"))
        assert len(v) == 1
        assert v[0].severity.value == "warning"

    def test_invalid_regex_in_feed_is_skipped(self, monkeypatch):
        # One bad pattern shouldn't kill the whole rule
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed(
            {
                "id": "bad",
                "title": "bad",
                "regex": r"(?P<incomplete",
                "severity": "HIGH",
            },
            {
                "id": "good",
                "title": "good",
                "regex": r"goodmatch",
                "severity": "HIGH",
            },
        )
        with self._patch(feed):
            v = self.rule.evaluate(_ctx("x = goodmatch in here"))
        # Only 'good' fires; 'bad' is silently skipped
        assert len(v) == 1
        assert "good" in v[0].message

    def test_caps_violations_per_file(self, monkeypatch):
        # Hit more than _MAX_VIOLATIONS_PER_FILE distinct rules → cap kicks in
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        # Build _MAX + 3 patterns, each matching a distinct token
        patterns = []
        tokens = []
        for i in range(_MAX_VIOLATIONS_PER_FILE + 3):
            tokens.append(f"TOKEN{i}_LITERAL")
            patterns.append({
                "id": f"rule-{i}",
                "title": f"rule {i}",
                "regex": rf"TOKEN{i}_LITERAL",
                "severity": "HIGH",
            })
        content = " ".join(tokens)
        with self._patch({"patterns": patterns}):
            v = self.rule.evaluate(_ctx(content))
        # Up to MAX violations + 1 truncation notice
        assert len(v) == _MAX_VIOLATIONS_PER_FILE + 1
        assert "truncated" in v[-1].message

    def test_no_match_no_violations(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "id": "aws-access-token",
            "title": "AWS access token",
            "regex": r"AKIA[0-9A-Z]{16}",
            "severity": "CRITICAL",
        })
        with self._patch(feed):
            assert self.rule.evaluate(_ctx("nothing matching here")) == []
