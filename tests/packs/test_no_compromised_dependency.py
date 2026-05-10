"""Tests for the no-compromised-dependency hybrid rule.

This rule is the first cloud-augmented rule in AgentLint. The tests verify:

  1. **Self-degrading**: with no AgentChute license configured, the rule
     is a silent no-op even when an install is in the deny list.
  2. **Hot-path activation**: when the deny list is populated AND the
     command installs a deny-listed package, an ERROR violation fires.
  3. **Package-name extraction** across npm, yarn, pnpm, pip, gem, cargo.
  4. **Negative cases**: clean installs, non-Bash commands, empty commands.
"""

from __future__ import annotations

from unittest.mock import patch

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.universal.no_compromised_dependency import (
    NoCompromisedDependency,
    _extract_packages,
)


def _ctx(command: str, tool_name: str = "Bash") -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input={"command": command},
        project_dir="/tmp/project",
        config={},
    )


# ---------- package-name extraction (regex correctness) ----------


class TestExtractPackages:
    def test_npm_install(self):
        assert _extract_packages("npm install express") == ["express"]
        assert _extract_packages("npm i lodash") == ["lodash"]
        assert _extract_packages("npm add @scoped/pkg") == ["@scoped/pkg"]

    def test_pip_install(self):
        assert _extract_packages("pip install requests") == ["requests"]
        assert _extract_packages("pip3 install Django") == ["django"]

    def test_yarn_pnpm(self):
        assert _extract_packages("yarn add react") == ["react"]
        assert _extract_packages("pnpm add typescript") == ["typescript"]

    def test_gem_cargo(self):
        assert _extract_packages("gem install rails") == ["rails"]
        assert _extract_packages("cargo install ripgrep") == ["ripgrep"]
        assert _extract_packages("cargo add serde") == ["serde"]

    def test_skips_flags(self):
        # `pip install -r requirements.txt` should not extract -r as a package
        assert _extract_packages("pip install -r requirements.txt") == []
        # `npm install` (no arg) should not extract anything
        assert _extract_packages("npm install") == []
        # `pip install -e .` (editable local install) should not flag
        assert _extract_packages("pip install -e .") == []

    def test_no_install_command(self):
        assert _extract_packages("ls -la") == []
        assert _extract_packages("git push origin main") == []
        assert _extract_packages("") == []


# ---------- self-degrading: rule is no-op without AgentChute ----------


class TestSelfDegrading:
    rule = NoCompromisedDependency()

    def test_no_op_when_no_license_key(self, monkeypatch):
        """No AGENTCHUTE_LICENSE_KEY → cloud_feed.get returns default
        empty set → rule produces zero violations."""
        monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)
        ctx = _ctx("npm install evilpackage")
        assert self.rule.evaluate(ctx) == []

    def test_no_op_when_deny_list_empty(self, monkeypatch, tmp_path):
        """Even with a license key set, an empty deny list = zero violations."""
        feeds_dir = tmp_path / "feeds"
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
        monkeypatch.setenv("AGENTLINT_FEEDS_DIR", str(feeds_dir))

        # Stub cloud_feed.get to return an empty list
        with patch(
            "agentlint.agentchute.cloud_feed.get", return_value=set()
        ) as mock_get:
            ctx = _ctx("pip install requests")
            assert self.rule.evaluate(ctx) == []
        # Rule SHOULD have consulted the feed (proves the cloud path is wired)
        # but only if there are packages to check
        mock_get.assert_called_once_with(
            "compromised-packages", default=set(), allow_network=False
        )

    def test_no_op_for_non_bash(self):
        ctx = _ctx("npm install evil", tool_name="Write")
        assert self.rule.evaluate(ctx) == []

    def test_no_op_for_empty_command(self):
        ctx = _ctx("")
        assert self.rule.evaluate(ctx) == []


# ---------- happy path: deny-listed package triggers ERROR ----------


class TestHappyPath:
    rule = NoCompromisedDependency()

    def _patch_feed(self, deny_list):
        return patch(
            "agentlint.agentchute.cloud_feed.get",
            return_value=deny_list,
        )

    def test_blocks_npm_install_of_deny_listed_package(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
        deny = ["evilpackage", "@malicious/lib"]
        with self._patch_feed(deny):
            ctx = _ctx("npm install evilpackage")
            violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].rule_id == "no-compromised-dependency"
        assert "evilpackage" in violations[0].message
        assert violations[0].severity.value == "error"
        assert "incidents@agentchute.io" in violations[0].suggestion

    def test_blocks_pip_install_of_deny_listed_package(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
        deny = ["leftpad-injected"]
        with self._patch_feed(deny):
            ctx = _ctx("pip install leftpad-injected")
            violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "leftpad-injected" in violations[0].message

    def test_allows_clean_packages(self, monkeypatch):
        """When the install isn't on the deny list, no violation."""
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
        deny = ["only-this-one-is-bad"]
        with self._patch_feed(deny):
            ctx = _ctx("npm install lodash")
            violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_handles_scoped_npm_packages(self, monkeypatch):
        """@org/pkg scoped packages can also be on the deny list."""
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
        deny = ["@malicious/lib"]
        with self._patch_feed(deny):
            ctx = _ctx("npm install @malicious/lib")
            violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "@malicious/lib" in violations[0].message

    def test_accepts_set_or_list_or_tuple(self, monkeypatch):
        """The deny-list payload may arrive as set/list/tuple from JSON.
        All three forms must work."""
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
        for shape in (
            ["evil"],
            ("evil",),
            {"evil"},
        ):
            with self._patch_feed(shape):
                ctx = _ctx("npm install evil")
                violations = self.rule.evaluate(ctx)
            assert len(violations) == 1, f"failed for shape {type(shape).__name__}"


# ---------- multiple installs in one command ----------


def test_multiple_packages_in_one_command(monkeypatch):
    """`npm install foo` + `pip install bar` separated by `&&` should
    catch both if both are deny-listed."""
    rule = NoCompromisedDependency()
    monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test_xxx")
    deny = ["foo", "bar"]
    with patch("agentlint.agentchute.cloud_feed.get", return_value=deny):
        ctx = _ctx("npm install foo && pip install bar")
        violations = rule.evaluate(ctx)
    pkg_names = {v.message.split("'")[1] for v in violations}
    assert "foo" in pkg_names
    assert "bar" in pkg_names
