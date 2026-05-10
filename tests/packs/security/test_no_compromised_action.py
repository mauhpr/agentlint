"""Tests for no-compromised-action (Phase 19, security pack).

Hybrid rule: parses GitHub workflow YAMLs for ``uses: <repo>@<ref>``
and flags refs whose action has open GHSA advisories.

Verifies:
  1. _looks_like_workflow gating: only applies to workflow files.
  2. _extract_uses parses common forms; skips local/docker refs.
  3. SHA-pin handling: still warns (can't verify SHA against range).
  4. Version-range filtering: refs past the fix don't fire.
  5. Self-degrading: no license OR empty feed → no violations.
"""

from __future__ import annotations

from unittest.mock import patch

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.security.no_compromised_action import (
    NoCompromisedAction,
    _extract_uses,
    _looks_like_workflow,
    _ref_looks_like_sha,
)


def _ctx(content: str, *, file_path: str = ".github/workflows/ci.yml",
         tool: str = "Write") -> RuleContext:
    tool_input: dict = {"file_path": file_path}
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


# ---------- _looks_like_workflow ----------


class TestLooksLikeWorkflow:
    def test_dotgithub_path(self):
        assert _looks_like_workflow(".github/workflows/ci.yml", "uses: foo/bar")

    def test_yml_with_uses(self):
        assert _looks_like_workflow("/some/dir/file.yml", "uses: foo/bar")

    def test_arbitrary_yml_no_uses(self):
        assert _looks_like_workflow("config.yml", "name: hello") is False

    def test_no_path_with_workflow_keys(self):
        # Heuristic fallback: presence of jobs: + uses:
        assert _looks_like_workflow(None, "jobs:\n  test:\n    uses: foo/bar")

    def test_python_file(self):
        assert _looks_like_workflow("/x.py", "uses: foo/bar  # not yaml") is False


# ---------- _extract_uses ----------


class TestExtractUses:
    def test_basic_tag(self):
        content = "      uses: tj-actions/changed-files@v44"
        assert _extract_uses(content) == [("tj-actions/changed-files", "v44")]

    def test_sha_pin(self):
        sha = "a" * 40
        content = f"      uses: tj-actions/changed-files@{sha}"
        out = _extract_uses(content)
        assert out == [("tj-actions/changed-files", sha)]

    def test_no_ref(self):
        # ``uses: foo/bar`` (no @ref) — defaults to master upstream
        content = "      uses: actions/checkout"
        assert _extract_uses(content) == [("actions/checkout", None)]

    def test_skips_overlong_repo(self):
        content = "      uses: " + ("o" * 201) + "/repo@v1"
        assert _extract_uses(content) == []

    def test_dedup(self):
        content = """
        uses: actions/checkout@v4
        uses: actions/checkout@v4
        """
        assert _extract_uses(content) == [("actions/checkout", "v4")]

    def test_multiple_distinct(self):
        content = """
        uses: actions/checkout@v4
        uses: tj-actions/changed-files@v44
        """
        out = _extract_uses(content)
        assert ("actions/checkout", "v4") in out
        assert ("tj-actions/changed-files", "v44") in out

    def test_skips_local_ref(self):
        content = "        uses: ./.github/actions/local-action"
        assert _extract_uses(content) == []


# ---------- _ref_looks_like_sha ----------


def test_ref_sha_detection():
    assert _ref_looks_like_sha("a" * 40)
    assert _ref_looks_like_sha("0123456789abcdef" * 2 + "01234567")  # 40 chars
    assert not _ref_looks_like_sha("v44")
    assert not _ref_looks_like_sha("a" * 39)
    assert not _ref_looks_like_sha("Z" * 40)  # non-hex


# ---------- self-degrading ----------


class TestSelfDegrading:
    rule = NoCompromisedAction()

    def test_no_license(self, monkeypatch):
        monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)
        ctx = _ctx("uses: tj-actions/changed-files@v44")
        assert self.rule.evaluate(ctx) == []

    def test_empty_feed(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with patch("agentlint.agentchute.cloud_feed.get",
                   return_value={"actions": []}):
            assert self.rule.evaluate(
                _ctx("uses: tj-actions/changed-files@v44")
            ) == []

    def test_non_workflow_file(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with patch("agentlint.agentchute.cloud_feed.get",
                   return_value={"actions": [{"repo": "foo/bar"}]}):
            ctx = _ctx("uses: foo/bar@v1", file_path="/some/randomfile.py")
            assert self.rule.evaluate(ctx) == []

    def test_non_file_tool(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "uses: foo/bar"},
            project_dir="/tmp",
            config={},
        )
        assert self.rule.evaluate(ctx) == []

    def test_empty_content_and_non_dict_feed(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        assert self.rule.evaluate(_ctx("")) == []
        with patch("agentlint.agentchute.cloud_feed.get", return_value=[]):
            assert self.rule.evaluate(_ctx("uses: foo/bar@v1")) == []


# ---------- happy path ----------


class TestHappyPath:
    rule = NoCompromisedAction()

    def _feed(self, *actions):
        return {"actions": list(actions)}

    def _patch(self, feed):
        return patch("agentlint.agentchute.cloud_feed.get", return_value=feed)

    def test_blocks_vulnerable_version(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "repo": "tj-actions/changed-files",
            "vulnerable_versions": [
                {"events": [{"introduced": "0"}, {"fixed": "46.0.0"}]}
            ],
            "ghsa_id": "GHSA-mw4p-6x4p-x5m5",
            "severity": "CRITICAL",
            "summary": "Hijacked Action exfiltrates secrets",
        })
        with self._patch(feed):
            v = self.rule.evaluate(_ctx(
                "      uses: tj-actions/changed-files@v44"
            ))
        assert len(v) == 1
        assert v[0].rule_id == "no-compromised-action"
        assert "tj-actions/changed-files" in v[0].message
        assert "GHSA-mw4p-6x4p-x5m5" in v[0].message
        assert v[0].severity.value == "error"

    def test_allows_fixed_version(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "repo": "tj-actions/changed-files",
            "vulnerable_versions": [
                {"events": [{"introduced": "0"}, {"fixed": "46.0.0"}]}
            ],
            "ghsa_id": "GHSA-mw4p-6x4p-x5m5",
            "severity": "CRITICAL",
        })
        with self._patch(feed):
            v = self.rule.evaluate(_ctx(
                "      uses: tj-actions/changed-files@v46.0.1"
            ))
        assert v == []

    def test_sha_pin_still_fires(self, monkeypatch):
        # Even if the user pinned to a SHA, we can't verify it's safe
        # — surface the advisory anyway.
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        sha = "a" * 40
        feed = self._feed({
            "repo": "tj-actions/changed-files",
            "vulnerable_versions": [{"events": [{"introduced": "0"}]}],
            "ghsa_id": "GHSA-x",
            "severity": "HIGH",
        })
        with self._patch(feed):
            v = self.rule.evaluate(_ctx(
                f"      uses: tj-actions/changed-files@{sha}"
            ))
        assert len(v) == 1

    def test_no_ref_surfaces_advisory(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "repo": "actions/checkout",
            "vulnerable_versions": [{"events": [{"introduced": "0"}]}],
            "ghsa_id": "GHSA-no-ref",
            "severity": "HIGH",
        })
        with self._patch(feed):
            v = self.rule.evaluate(_ctx("      uses: actions/checkout"))
        assert len(v) == 1
        assert "(no ref)" in v[0].message

    def test_edit_tool_uses_new_string_and_skips_malformed_records(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed(
            "bad",
            {},
            {
                "repo": "actions/setup-python",
                "vulnerable_versions": [{"events": [{"introduced": "0"}]}],
                "ghsa_id": "GHSA-python",
            },
        )
        with self._patch(feed):
            v = self.rule.evaluate(_ctx("uses: actions/setup-python@v1", tool="Edit"))
        assert len(v) == 1

    def test_unrelated_action_not_flagged(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "repo": "tj-actions/changed-files",
            "vulnerable_versions": [{"events": [{"introduced": "0"}]}],
            "ghsa_id": "GHSA-x",
            "severity": "HIGH",
        })
        with self._patch(feed):
            v = self.rule.evaluate(_ctx(
                "      uses: actions/checkout@v4"
            ))
        assert v == []
