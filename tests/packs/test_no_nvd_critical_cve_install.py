"""Tests for the NVD critical-CVE hybrid rule."""

from __future__ import annotations

import builtins
from unittest.mock import patch

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.universal.no_nvd_critical_cve_install import (
    NoNvdCriticalCveInstall,
    VersionedArtifact,
    _cpe_product_versions,
    _critical_cpe_index,
    _docker_artifact,
    _extract_versioned_artifacts,
    _is_blocking_cve,
    _package_name_variants,
    _version_variants,
)


def _ctx(command: str, tool_name: str = "Bash") -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input={"command": command},
        project_dir="/tmp/project",
        config={},
    )


class TestExtraction:
    def test_extracts_pinned_package_installs(self):
        assert VersionedArtifact("lodash", "4.17.20") in _extract_versioned_artifacts(
            "npm install lodash@4.17.20"
        )
        assert VersionedArtifact("requests", "2.25.0") in _extract_versioned_artifacts(
            "pip install requests==2.25.0"
        )
        assert VersionedArtifact("ripgrep", "13.0.0") in _extract_versioned_artifacts(
            "cargo install ripgrep --version 13.0.0"
        )

    def test_extracts_docker_and_apt_versions(self):
        assert _extract_versioned_artifacts("docker pull nginx:1.24.0") == [
            VersionedArtifact("nginx", "1.24.0")
        ]
        assert VersionedArtifact("openssl", "1.1.1f-1ubuntu2") in _extract_versioned_artifacts(
            "apt-get install openssl=1.1.1f-1ubuntu2"
        )

    def test_skips_unpinned_and_latest(self):
        assert _extract_versioned_artifacts("npm install lodash") == []
        assert _extract_versioned_artifacts("docker pull nginx:latest") == []
        assert _extract_versioned_artifacts("ls -la") == []
        assert _docker_artifact("nginx") is None

    def test_scoped_packages_include_basename_variant(self):
        artifacts = _extract_versioned_artifacts("npm i @scope/pkg@1.2.3")
        assert VersionedArtifact("scope/pkg", "1.2.3") in artifacts
        assert VersionedArtifact("pkg", "1.2.3") in artifacts
        assert _package_name_variants("@") == set()


class TestNvdFeedHelpers:
    def test_version_variants_keep_full_and_upstream_forms(self):
        assert _version_variants("v1.1.1f-1ubuntu2") == {
            "v1.1.1f-1ubuntu2",
            "1.1.1f-1ubuntu2",
            "1.1.1f",
        }
        assert _version_variants("*") == set()

    def test_cpe_23_parsing(self):
        assert _cpe_product_versions("cpe:2.3:a:nginx:nginx:1.24.0:*:*:*:*:*:*:*") == [
            VersionedArtifact("nginx", "1.24.0")
        ]

    def test_cpe_23_handles_escaped_fields_and_malformed_values(self):
        assert _cpe_product_versions(r"cpe:2.3:a:acme:weird\:pkg:2.0.0:*:*:*:*:*:*:*") == [
            VersionedArtifact("weird-pkg", "2.0.0")
        ]
        assert _cpe_product_versions("not-a-cpe") == []

    def test_legacy_cpe_uri_parsing(self):
        assert _cpe_product_versions("cpe:/a:openssl:openssl:1.1.1f") == [
            VersionedArtifact("openssl", "1.1.1f")
        ]

    def test_blocking_cve_requires_critical_or_cisa(self):
        assert _is_blocking_cve({"severity": "CRITICAL"})
        assert _is_blocking_cve({"severity": "HIGH", "metadata": {"cisa": {"cisaExploitAdd": "2026-01-01"}}})
        assert not _is_blocking_cve({"severity": "HIGH", "metadata": {"cisa": {}}})

    def test_critical_cpe_index_skips_non_blocking_and_malformed_records(self):
        records = [
            "bad",
            {"severity": "HIGH", "metadata": {"cpe_matches": ["cpe:2.3:a:nginx:nginx:1.24.0:*:*:*:*:*:*:*"]}},
            {
                "cve_id": "CVE-2026-0001",
                "severity": "CRITICAL",
                "metadata": {"cpe_matches": ["cpe:2.3:a:nginx:nginx:1.24.0:*:*:*:*:*:*:*"]},
            },
        ]
        index = _critical_cpe_index(records)
        assert VersionedArtifact("nginx", "1.24.0") in index
        assert index[VersionedArtifact("nginx", "1.24.0")][0]["cve_id"] == "CVE-2026-0001"


class TestRule:
    rule = NoNvdCriticalCveInstall()

    def _feed(self, *records):
        return {"records": list(records)}

    def test_no_op_without_license_or_feed(self, monkeypatch):
        monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)
        assert self.rule.evaluate(_ctx("docker pull nginx:1.24.0")) == []

        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with patch("agentlint.agentchute.cloud_feed.get", return_value={"records": []}):
            assert self.rule.evaluate(_ctx("docker pull nginx:1.24.0")) == []

    def test_no_op_for_non_bash_and_non_dict_feed(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        assert self.rule.evaluate(_ctx("docker pull nginx:1.24.0", tool_name="Write")) == []
        assert self.rule.evaluate(_ctx("npm install lodash")) == []
        with patch("agentlint.agentchute.cloud_feed.get", return_value=[]):
            assert self.rule.evaluate(_ctx("docker pull nginx:1.24.0")) == []

    def test_no_op_when_agentchute_module_is_missing(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        real_import = builtins.__import__

        def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "agentlint.agentchute" and fromlist == ("cloud_feed",):
                raise ImportError("agentchute unavailable")
            return real_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=fake_import):
            assert self.rule.evaluate(_ctx("docker pull nginx:1.24.0")) == []

    def test_blocks_exact_critical_cpe_match(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "cve_id": "CVE-2026-0001",
            "severity": "CRITICAL",
            "summary": "Critical nginx overflow",
            "metadata": {
                "cpe_matches": ["cpe:2.3:a:nginx:nginx:1.24.0:*:*:*:*:*:*:*"],
            },
        })
        with patch("agentlint.agentchute.cloud_feed.get", return_value=feed):
            violations = self.rule.evaluate(_ctx("docker pull nginx:1.24.0"))
        assert len(violations) == 1
        assert violations[0].rule_id == "no-nvd-critical-cve-install"
        assert "CVE-2026-0001" in violations[0].message
        assert "Critical nginx overflow" in violations[0].message
        assert violations[0].severity.value == "error"

    def test_blocks_cisa_kev_even_when_not_critical(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "cve_id": "CVE-2026-0002",
            "severity": "HIGH",
            "metadata": {
                "cisa": {"cisaExploitAdd": "2026-01-01"},
                "cpe_matches": ["cpe:2.3:a:openssl:openssl:1.1.1f:*:*:*:*:*:*:*"],
            },
        })
        with patch("agentlint.agentchute.cloud_feed.get", return_value=feed):
            violations = self.rule.evaluate(_ctx("apt-get install openssl=1.1.1f-1ubuntu2"))
        assert len(violations) == 1
        assert "CVE-2026-0002" in violations[0].message

    def test_allows_non_critical_non_kev_and_different_versions(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed(
            {
                "cve_id": "CVE-2026-0003",
                "severity": "HIGH",
                "metadata": {"cpe_matches": ["cpe:2.3:a:nginx:nginx:1.24.0:*:*:*:*:*:*:*"]},
            },
            {
                "cve_id": "CVE-2026-0004",
                "severity": "CRITICAL",
                "metadata": {"cpe_matches": ["cpe:2.3:a:redis:redis:6.2.0:*:*:*:*:*:*:*"]},
            },
        )
        with patch("agentlint.agentchute.cloud_feed.get", return_value=feed):
            assert self.rule.evaluate(_ctx("docker pull nginx:1.24.0")) == []
            assert self.rule.evaluate(_ctx("docker pull redis:6.2.1")) == []
