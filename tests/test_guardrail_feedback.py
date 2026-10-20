"""End-to-end corrections for the October guardrail usability reports."""

import pytest

from agentlint.adapters.codex_patch import PatchError, _path, _update
from agentlint.cli import _patch_violation


def test_boundary_failure_names_selected_project_and_distinguishes_os_permissions(tmp_path):
    project = tmp_path / "selected"
    project.mkdir()
    target = tmp_path / "receipt.json"
    with pytest.raises(PatchError) as raised:
        _path(str(target), project, project)
    violation = _patch_violation(raised.value)
    assert str(project) in violation.message
    assert violation.file_path == str(target)
    assert "inspection error" in violation.message.lower()
    assert "OS writable roots" in violation.suggestion


def test_named_function_anchor_bounds_repeated_mock_context():
    before = "def test_first():\n    check(1)\n\ndef test_second():\n    check(1)\n"
    after = _update(before, ["@@ def test_first():", "-    check(1)", "+    check(2)"])
    assert after == before.replace("check(1)", "check(2)", 1)


def test_repeated_context_within_named_function_stays_ambiguous():
    before = "def test_first():\n    check(1)\n    check(1)\n"
    with pytest.raises(PatchError, match="ambiguous"):
        _update(before, ["@@ def test_first():", "-    check(1)", "+    check(2)"])


def test_python_anchor_does_not_prefer_local_whitespace_match_over_native_exact_match():
    before = "def test_first():\n    check(1)   \n\ndef test_second():\n    check(1)\n"
    with pytest.raises(PatchError, match="not found"):
        _update(before, ["@@ def test_first():", "-    check(1)", "+    check(2)"])
