"""Tests for the no-vulnerable-version-install hybrid rule.

Sibling to no-compromised-dependency. Where that one matches package
NAMES, this one matches package (NAME, VERSION) against GHSA ranges.

Verifies:
  1. Self-degrading: no license key OR empty feed → zero violations.
  2. Pinned-install extraction across npm/yarn/pnpm/pip/cargo.
  3. Version-range matching against OSV-format ranges.
  4. Negative cases: unpinned installs, non-Bash commands, fixed versions.
"""

from __future__ import annotations

from unittest.mock import patch

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.universal.no_vulnerable_version_install import (
    NoVulnerableVersionInstall,
    _extract_pinned_installs,
    _matches_any_range,
    _parse_version,
)


def _ctx(command: str, tool_name: str = "Bash") -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input={"command": command},
        project_dir="/tmp/project",
        config={},
    )


# ---------- pinned-install extraction ----------


class TestExtract:
    def test_npm_at_pin(self):
        assert _extract_pinned_installs("npm install lodash@4.17.20") == [
            ("npm", "lodash", "4.17.20")
        ]

    def test_npm_scoped_at_pin(self):
        # @scope/pkg@1.2.3 — the package contains @ already
        out = _extract_pinned_installs("npm i @types/node@18.0.0")
        assert ("npm", "@types/node", "18.0.0") in out

    def test_yarn_pnpm(self):
        assert ("npm", "react", "17.0.2") in _extract_pinned_installs(
            "yarn add react@17.0.2"
        )
        assert ("npm", "typescript", "5.0.0") in _extract_pinned_installs(
            "pnpm add typescript@5.0.0"
        )

    def test_pip_eqeq(self):
        assert _extract_pinned_installs("pip install requests==2.25.0") == [
            ("PyPI", "requests", "2.25.0")
        ]

    def test_cargo_version_flag(self):
        assert _extract_pinned_installs(
            "cargo install ripgrep --version 13.0.0"
        ) == [("crates.io", "ripgrep", "13.0.0")]

    def test_skips_unpinned(self):
        # An unpinned npm install should NOT be flagged here — that's
        # dependency-hygiene's job. We only care about pinned installs.
        assert _extract_pinned_installs("npm install lodash") == []
        assert _extract_pinned_installs("pip install django") == []

    def test_no_install(self):
        assert _extract_pinned_installs("ls -la") == []
        assert _extract_pinned_installs("git push origin main") == []
        assert _extract_pinned_installs("") == []


# ---------- version comparison ----------


class TestVersionParsing:
    def test_basic(self):
        assert _parse_version("1.2.3") == (1, 2, 3)
        assert _parse_version("0.0.1") == (0, 0, 1)

    def test_v_prefix(self):
        assert _parse_version("v1.0.0") == (1, 0, 0)

    def test_prerelease(self):
        # Crude tuple: pre-release suffixes lose their tag, only digits remain
        assert _parse_version("2.0.0-beta.1") == (2, 0, 0, 1)

    def test_unparseable(self):
        assert _parse_version("weirdstring") == (0,)

    def test_empty(self):
        assert _parse_version("") == (0,)


class TestRangeMatching:
    def test_introduced_only_matches(self):
        # range = [{"introduced": "0"}] means "everything from 0 onward"
        assert _matches_any_range(
            (1, 2, 3),
            [{"events": [{"introduced": "0"}]}],
        )

    def test_below_introduced_misses(self):
        assert not _matches_any_range(
            (0, 5, 0),
            [{"events": [{"introduced": "1.0.0"}]}],
        )

    def test_introduced_fixed_window(self):
        # vulnerable in [1.0.0, 2.0.0)
        ranges = [{"events": [{"introduced": "1.0.0"}, {"fixed": "2.0.0"}]}]
        assert _matches_any_range((1, 0, 0), ranges)
        assert _matches_any_range((1, 5, 7), ranges)
        assert not _matches_any_range((2, 0, 0), ranges)
        assert not _matches_any_range((0, 9, 9), ranges)

    def test_last_affected(self):
        ranges = [{"events": [{"introduced": "1.0.0"}, {"last_affected": "1.5.0"}]}]
        assert _matches_any_range((1, 5, 0), ranges)
        assert not _matches_any_range((1, 5, 1), ranges)

    def test_multiple_ranges_or(self):
        ranges = [
            {"events": [{"introduced": "1.0.0"}, {"fixed": "1.2.0"}]},
            {"events": [{"introduced": "2.0.0"}, {"fixed": "2.1.0"}]},
        ]
        assert _matches_any_range((1, 1, 0), ranges)
        assert _matches_any_range((2, 0, 5), ranges)
        assert not _matches_any_range((1, 5, 0), ranges)
        assert not _matches_any_range((3, 0, 0), ranges)


# ---------- self-degrading ----------


class TestSelfDegrading:
    rule = NoVulnerableVersionInstall()

    def test_no_op_when_no_license_key(self, monkeypatch):
        monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)
        ctx = _ctx("npm install lodash@4.17.20")
        assert self.rule.evaluate(ctx) == []

    def test_no_op_when_feed_empty(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with patch(
            "agentlint.agentchute.cloud_feed.get",
            return_value={"records": []},
        ):
            ctx = _ctx("npm install lodash@4.17.20")
            assert self.rule.evaluate(ctx) == []

    def test_no_op_for_non_bash(self):
        ctx = _ctx("npm install bad@1.0.0", tool_name="Write")
        assert self.rule.evaluate(ctx) == []

    def test_no_op_for_unpinned(self, monkeypatch):
        # Even with a populated feed, unpinned installs aren't flagged here.
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = {
            "records": [{
                "ecosystem": "npm",
                "package": "lodash",
                "vulnerable_versions": [
                    {"events": [{"introduced": "0"}, {"fixed": "5.0.0"}]}
                ],
                "ghsa_id": "GHSA-xxxx",
                "severity": "HIGH",
            }],
        }
        with patch("agentlint.agentchute.cloud_feed.get", return_value=feed):
            assert self.rule.evaluate(_ctx("npm install lodash")) == []


# ---------- happy path ----------


class TestHappyPath:
    rule = NoVulnerableVersionInstall()

    def _feed(self, *records):
        return {"records": list(records)}

    def _patch(self, feed):
        return patch("agentlint.agentchute.cloud_feed.get", return_value=feed)

    def test_blocks_vulnerable_npm_version(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "ecosystem": "npm",
            "package": "lodash",
            "vulnerable_versions": [
                {"events": [{"introduced": "0"}, {"fixed": "4.17.21"}]}
            ],
            "ghsa_id": "GHSA-29mw-wpgm-hmr9",
            "severity": "HIGH",
            "summary": "Prototype pollution in lodash",
        })
        with self._patch(feed):
            violations = self.rule.evaluate(_ctx("npm install lodash@4.17.20"))
        assert len(violations) == 1
        v = violations[0]
        assert v.rule_id == "no-vulnerable-version-install"
        assert "lodash" in v.message
        assert "GHSA-29mw-wpgm-hmr9" in v.message
        assert "Prototype pollution" in v.message
        assert v.severity.value == "error"

    def test_allows_fixed_version(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "ecosystem": "npm",
            "package": "lodash",
            "vulnerable_versions": [
                {"events": [{"introduced": "0"}, {"fixed": "4.17.21"}]}
            ],
            "ghsa_id": "GHSA-29mw-wpgm-hmr9",
            "severity": "HIGH",
        })
        with self._patch(feed):
            assert self.rule.evaluate(_ctx("npm install lodash@4.17.21")) == []

    def test_blocks_pip_eqeq(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "ecosystem": "PyPI",
            "package": "requests",
            "vulnerable_versions": [
                {"events": [{"introduced": "2.0.0"}, {"fixed": "2.30.0"}]}
            ],
            "ghsa_id": "GHSA-9wx4-h78v-vm56",
            "severity": "MEDIUM",
        })
        with self._patch(feed):
            violations = self.rule.evaluate(_ctx("pip install requests==2.25.0"))
        assert len(violations) == 1

    def test_unrelated_package_not_flagged(self, monkeypatch):
        # Same ecosystem + version, different package name: must not match.
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "ecosystem": "npm",
            "package": "lodash",
            "vulnerable_versions": [
                {"events": [{"introduced": "0"}, {"fixed": "5.0.0"}]}
            ],
            "ghsa_id": "GHSA-x",
        })
        with self._patch(feed):
            assert self.rule.evaluate(_ctx("npm install express@4.17.0")) == []

    def test_one_violation_per_install(self, monkeypatch):
        # Even if the same package has multiple advisories, we only emit
        # one violation (they're tighter than a list).
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed(
            {
                "ecosystem": "npm",
                "package": "lodash",
                "vulnerable_versions": [{"events": [{"introduced": "0"}]}],
                "ghsa_id": "GHSA-a",
                "severity": "HIGH",
            },
            {
                "ecosystem": "npm",
                "package": "lodash",
                "vulnerable_versions": [{"events": [{"introduced": "1.0.0"}]}],
                "ghsa_id": "GHSA-b",
                "severity": "MEDIUM",
            },
        )
        with self._patch(feed):
            violations = self.rule.evaluate(_ctx("npm install lodash@4.17.20"))
        assert len(violations) == 1
