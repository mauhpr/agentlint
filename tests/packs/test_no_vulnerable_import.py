"""Tests for no-vulnerable-import (Phase 19, hybrid).

Sibling to no-vulnerable-version-install: same GHSA feed, different
match logic. Where the install rule cares about pinned versions, this
rule fires whenever an imported package has any open advisory.

Verifies:
  1. JS / TS / Python import extraction across common forms.
  2. Self-degrading: no license OR empty feed → no violations.
  3. Negative cases: imports of unrelated packages, stdlib, relative paths.
  4. Edit + Write tool surfaces.
  5. One violation per (file, package) — picks highest severity.
"""

from __future__ import annotations

from unittest.mock import patch

from agentlint.models import HookEvent, RuleContext
from agentlint.packs.universal.no_vulnerable_import import (
    NoVulnerableImport,
    _extract_imports,
    _strip_js_pkg,
)


def _ctx(content: str, *, tool: str = "Write", file_path: str | None = None) -> RuleContext:
    tool_input: dict = {"file_path": file_path or "/tmp/x.js"}
    if tool == "Edit":
        tool_input["new_string"] = content
    else:
        tool_input["content"] = content
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool,
        tool_input=tool_input,
        project_dir="/tmp/project",
        config={},
    )


# ---------- _strip_js_pkg ----------


class TestStripJsPkg:
    def test_bare(self):
        assert _strip_js_pkg("react") == "react"

    def test_subpath(self):
        assert _strip_js_pkg("react/jsx-runtime") == "react"

    def test_scoped(self):
        assert _strip_js_pkg("@types/node") == "@types/node"

    def test_scoped_with_subpath(self):
        assert _strip_js_pkg("@scope/pkg/sub") == "@scope/pkg"

    def test_relative(self):
        assert _strip_js_pkg("./local") is None
        assert _strip_js_pkg("../up") is None
        assert _strip_js_pkg("/abs") is None

    def test_node_builtin(self):
        assert _strip_js_pkg("node:fs") is None

    def test_lower_cases(self):
        assert _strip_js_pkg("React") == "react"


# ---------- _extract_imports ----------


class TestExtractImports:
    def test_js_named_import(self):
        content = "import React from 'react';"
        assert ("npm", "react") in _extract_imports(content, "/x.jsx")

    def test_js_side_effect_import(self):
        content = "import 'normalize.css';"
        assert ("npm", "normalize.css") in _extract_imports(content, "/x.tsx")

    def test_js_require(self):
        content = "const lodash = require('lodash');"
        assert ("npm", "lodash") in _extract_imports(content, "/x.js")

    def test_js_dynamic_import(self):
        content = "const m = import('chalk');"
        assert ("npm", "chalk") in _extract_imports(content, "/x.js")

    def test_skips_relative(self):
        content = "import x from './local';"
        assert _extract_imports(content, "/x.js") == []

    def test_python_import(self):
        content = "import requests"
        assert ("PyPI", "requests") in _extract_imports(content, "/x.py")

    def test_python_from_import(self):
        content = "from django.contrib import auth"
        assert ("PyPI", "django") in _extract_imports(content, "/x.py")

    def test_python_skips_stdlib(self):
        content = "import os\nimport sys\nimport json"
        assert _extract_imports(content, "/x.py") == []

    def test_python_third_party_alongside_stdlib(self):
        content = "import os\nimport requests"
        out = _extract_imports(content, "/x.py")
        assert ("PyPI", "requests") in out
        # stdlib excluded
        assert ("PyPI", "os") not in out

    def test_dedup(self):
        content = "import x from 'react';\nimport y from 'react';"
        out = _extract_imports(content, "/x.js")
        assert out.count(("npm", "react")) == 1

    def test_unknown_extension_with_js_signal(self):
        # File without recognizable extension but content looks JS
        content = "const m = require('lodash');"
        assert ("npm", "lodash") in _extract_imports(content, "/no-extension")


# ---------- self-degrading ----------


class TestSelfDegrading:
    rule = NoVulnerableImport()

    def test_no_license_key(self, monkeypatch):
        monkeypatch.delenv("AGENTCHUTE_LICENSE_KEY", raising=False)
        ctx = _ctx("import x from 'lodash';")
        assert self.rule.evaluate(ctx) == []

    def test_empty_feed(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        with patch("agentlint.agentchute.cloud_feed.get", return_value={"records": []}):
            assert self.rule.evaluate(_ctx("import x from 'lodash';")) == []

    def test_non_file_tool(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "import lodash"},
            project_dir="/tmp",
            config={},
        )
        assert self.rule.evaluate(ctx) == []

    def test_empty_content(self):
        ctx = _ctx("", file_path="/x.js")
        assert self.rule.evaluate(ctx) == []


# ---------- happy path ----------


class TestHappyPath:
    rule = NoVulnerableImport()

    def _feed(self, *records):
        return {"records": list(records)}

    def _patch(self, feed):
        return patch("agentlint.agentchute.cloud_feed.get", return_value=feed)

    def test_warns_on_vulnerable_import(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "ecosystem": "npm",
            "package": "lodash",
            "vulnerable_versions": [{"events": [{"introduced": "0"}]}],
            "ghsa_id": "GHSA-29mw-wpgm-hmr9",
            "severity": "HIGH",
            "summary": "Prototype pollution in lodash",
        })
        with self._patch(feed):
            v = self.rule.evaluate(_ctx("import x from 'lodash';", file_path="/a.js"))
        assert len(v) == 1
        assert v[0].rule_id == "no-vulnerable-import"
        assert "lodash" in v[0].message
        assert "GHSA-29mw-wpgm-hmr9" in v[0].message
        assert v[0].severity.value == "warning"

    def test_picks_highest_severity_when_multiple_advisories(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed(
            {
                "ecosystem": "npm",
                "package": "react",
                "vulnerable_versions": [{"events": [{"introduced": "0"}]}],
                "ghsa_id": "GHSA-low",
                "severity": "LOW",
            },
            {
                "ecosystem": "npm",
                "package": "react",
                "vulnerable_versions": [{"events": [{"introduced": "0"}]}],
                "ghsa_id": "GHSA-critical",
                "severity": "CRITICAL",
            },
        )
        with self._patch(feed):
            v = self.rule.evaluate(_ctx("import React from 'react';", file_path="/a.tsx"))
        assert len(v) == 1
        assert "GHSA-critical" in v[0].message
        assert "CRITICAL" in v[0].message

    def test_unrelated_imports_not_flagged(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "ecosystem": "npm",
            "package": "lodash",
            "vulnerable_versions": [{"events": [{"introduced": "0"}]}],
            "ghsa_id": "GHSA-x",
            "severity": "HIGH",
        })
        with self._patch(feed):
            v = self.rule.evaluate(_ctx("import x from 'react';", file_path="/a.tsx"))
        assert v == []

    def test_works_for_edit_tool(self, monkeypatch):
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "ecosystem": "PyPI",
            "package": "requests",
            "vulnerable_versions": [{"events": [{"introduced": "0"}]}],
            "ghsa_id": "GHSA-9wx4-h78v-vm56",
            "severity": "MEDIUM",
        })
        with self._patch(feed):
            v = self.rule.evaluate(
                _ctx("import requests", tool="Edit", file_path="/x.py")
            )
        assert len(v) == 1
        assert "requests" in v[0].message

    def test_one_violation_per_package_per_file(self, monkeypatch):
        # Same package imported twice in one file → one violation
        monkeypatch.setenv("AGENTCHUTE_LICENSE_KEY", "ac_team_test")
        feed = self._feed({
            "ecosystem": "npm",
            "package": "lodash",
            "vulnerable_versions": [{"events": [{"introduced": "0"}]}],
            "ghsa_id": "GHSA-x",
            "severity": "HIGH",
        })
        with self._patch(feed):
            v = self.rule.evaluate(_ctx(
                "import _ from 'lodash';\nimport y from 'lodash/fp';",
                file_path="/a.js",
            ))
        assert len(v) == 1
