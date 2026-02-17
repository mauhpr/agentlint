"""Tests for stack auto-detection."""
from __future__ import annotations

import json

from agentlint.detector import detect_stack
from agentlint.packs import PACK_MODULES


class TestDetectStack:
    def test_empty_project_returns_universal(self, tmp_path):
        result = detect_stack(str(tmp_path))
        assert result == ["universal"]

    def test_python_detected_only_if_pack_registered(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        result = detect_stack(str(tmp_path))
        if "python" in PACK_MODULES:
            assert "python" in result
        else:
            # Python pack not registered yet, so detector should skip it
            assert "python" not in result

    def test_python_from_setup_py_only_if_registered(self, tmp_path):
        (tmp_path / "setup.py").write_text("from setuptools import setup\nsetup()\n")
        result = detect_stack(str(tmp_path))
        if "python" in PACK_MODULES:
            assert "python" in result
        else:
            assert "python" not in result

    def test_react_detected_only_if_pack_registered(self, tmp_path):
        pkg = {"dependencies": {"react": "^18.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        result = detect_stack(str(tmp_path))
        if "react" in PACK_MODULES:
            assert "react" in result
        else:
            assert "react" not in result

    def test_does_not_detect_react_without_react_dep(self, tmp_path):
        pkg = {"dependencies": {"express": "^4.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        result = detect_stack(str(tmp_path))
        assert "react" not in result

    def test_universal_always_first(self, tmp_path):
        result = detect_stack(str(tmp_path))
        assert result[0] == "universal"

    def test_only_returns_registered_packs(self, tmp_path):
        """All returned packs must exist in PACK_MODULES."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        pkg = {"dependencies": {"react": "^18.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        result = detect_stack(str(tmp_path))
        for pack in result:
            assert pack in PACK_MODULES

    def test_react_in_dev_dependencies(self, tmp_path):
        pkg = {"devDependencies": {"react": "^18.0.0"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        result = detect_stack(str(tmp_path))
        if "react" in PACK_MODULES:
            assert "react" in result
        else:
            assert "react" not in result

    def test_malformed_package_json(self, tmp_path):
        (tmp_path / "package.json").write_text("not valid json {{{")
        result = detect_stack(str(tmp_path))
        assert "react" not in result
        assert result == ["universal"]

    def test_package_json_without_dependencies_key(self, tmp_path):
        pkg = {"name": "my-app", "version": "1.0.0"}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        result = detect_stack(str(tmp_path))
        assert "react" not in result
