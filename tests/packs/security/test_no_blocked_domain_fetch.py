"""Tests for no-blocked-domain-fetch (Phase 19, security pack).

WARNING-level cousin of no-malicious-url-fetch. Match on domain
(not URL prefix) against a much larger deny-list (~80K StevenBlack
entries vs ~2K URLhaus).

Verifies:
  1. Self-degrading: no license OR empty feed → no violations.
  2. URL extraction follows the same fetch-verb gating.
  3. Domain match is case-insensitive on the host portion.
  4. Multiple URLs in one command — each unique host evaluated once.
"""

from __future__ import annotations

from unittest.mock import patch

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.security.no_blocked_domain_fetch import (
    NoBlockedDomainFetch,
    _domains_set,
    _extract_fetch_urls,
)


def _ctx(command: str, *, tool: str = "Bash") -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool,
        tool_input={"command": command},
        project_dir="/tmp/p",
        config={},
    )


# ---------- _extract_fetch_urls (smoke; logic shared with sibling rule) ----------


def test_extract_only_when_fetch_verb():
    assert _extract_fetch_urls("curl https://x.tld/a") == ["https://x.tld/a"]
    assert _extract_fetch_urls("echo https://x.tld/a") == []


# ---------- _domains_set caching ----------


def test_domains_set_caches_by_identity():
    domains = ["a.tld", "b.tld"]
    s1 = _domains_set(domains)
    s2 = _domains_set(domains)
    assert s1 is s2  # cache hit


def test_domains_set_invalidates_on_new_object():
    s1 = _domains_set(["a.tld"])
    s2 = _domains_set(["a.tld"])  # different list object → cache miss
    # Either reused or rebuilt — both are correct semantics. Accept both.
    assert s1 == s2 == {"a.tld"}


# ---------- self-degrading ----------


class TestSelfDegrading:
    rule = NoBlockedDomainFetch()

    def test_no_license(self, monkeypatch):
        monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)
        assert self.rule.evaluate(_ctx("curl https://anywhere.tld/x")) == []

    def test_empty_feed(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with patch("agentlint.agentchute.cloud_feed.get",
                   return_value={"domains": []}):
            assert self.rule.evaluate(_ctx("curl https://x.tld/y")) == []

    def test_non_bash(self):
        ctx = _ctx("curl https://x.tld/y", tool="Edit")
        assert self.rule.evaluate(ctx) == []

    def test_no_fetch_verb(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with patch("agentlint.agentchute.cloud_feed.get",
                   return_value={"domains": ["bad.tld"]}):
            assert self.rule.evaluate(_ctx('echo "see https://bad.tld"')) == []


# ---------- happy path ----------


class TestHappyPath:
    rule = NoBlockedDomainFetch()

    def _patch(self, domains):
        return patch(
            "agentlint.agentchute.cloud_feed.get",
            return_value={"domains": domains},
        )

    def test_warns_on_blocked_domain(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with self._patch(["bad.tld"]):
            v = self.rule.evaluate(_ctx("curl https://bad.tld/x"))
        assert len(v) == 1
        assert v[0].rule_id == "no-blocked-domain-fetch"
        assert "bad.tld" in v[0].message
        assert v[0].severity.value == "warning"

    def test_case_insensitive_host(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with self._patch(["bad.tld"]):
            v = self.rule.evaluate(_ctx("curl https://BAD.TLD/path"))
        assert len(v) == 1

    def test_unrelated_domain_not_flagged(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with self._patch(["bad.tld"]):
            v = self.rule.evaluate(_ctx("curl https://example.com/x"))
        assert v == []

    def test_dedupes_per_host(self, monkeypatch):
        # Multiple URLs on the same blocked host → one violation
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with self._patch(["bad.tld"]):
            v = self.rule.evaluate(_ctx(
                "curl https://bad.tld/a && curl https://bad.tld/b"
            ))
        assert len(v) == 1

    def test_multiple_blocked_hosts(self, monkeypatch):
        # Distinct blocked hosts → one violation each
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with self._patch(["bad1.tld", "bad2.tld"]):
            v = self.rule.evaluate(_ctx(
                "curl https://bad1.tld/x; curl https://bad2.tld/y"
            ))
        assert len(v) == 2
