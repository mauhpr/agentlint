"""End-to-end corrections for the October guardrail usability reports."""

from __future__ import annotations

import pytest

from agentlint.adapters.codex_patch import PatchError, _path, _read, _update
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


def test_missing_patch_input_has_read_error_correction(tmp_path):
    path = tmp_path / "missing.py"
    with pytest.raises(PatchError) as raised:
        _read(path)
    violation = _patch_violation(raised.value)
    assert violation.file_path == str(path)
    assert "read permissions" in violation.suggestion


def test_invalid_python_keeps_ambiguous_anchor_context_conservative():
    before = "def broken():\n    check(1)\n    ???\n    check(1)\n"
    with pytest.raises(PatchError, match="ambiguous"):
        _update(before, ["@@ def broken():", "-    check(1)", "+    check(2)"])


def test_non_definition_anchor_does_not_invent_a_python_scope():
    before = 'text = """\ndef described():\ncheck(1)\ncheck(1)\n"""\n'
    with pytest.raises(PatchError, match="ambiguous"):
        _update(before, ["@@ def described():", "-check(1)", "+check(2)"])


def test_exact_definition_anchor_wins_over_earlier_whitespace_variant():
    before = "def repeated():   \n    check(1)\n\ndef repeated():\n    check(1)\n"
    after = _update(before, ["@@ def repeated():", "-    check(1)", "+    check(2)"])
    assert after == "def repeated():   \n    check(1)\n\ndef repeated():\n    check(2)\n"


def test_indentation_in_definition_anchor_is_preserved():
    before = "class First:\n    def repeated():\n        check(1)\nclass Second:\n    def repeated():\n        check(1)\n"
    after = _update(before, ["@@     def repeated():", "-        check(1)", "+        check(2)"])
    assert after == before.replace("check(1)", "check(2)", 1)


def test_trailing_whitespace_in_anchor_marker_is_not_significant():
    before = "def repeated():   \n    check(1)\n\ndef repeated():\n    check(1)\n"
    after = _update(before, ["@@ def repeated():   ", "-    check(1)", "+    check(2)"])
    assert after == "def repeated():   \n    check(1)\n\ndef repeated():\n    check(2)\n"


def test_plain_section_anchors_remain_supported_without_python_scope_rules():
    before = "section A\nvalue=1\nsection B\nvalue=2\n"
    after = _update(before, ["@@ section A", "-value=1", "+value=3"])
    assert after == "section A\nvalue=3\nsection B\nvalue=2\n"
