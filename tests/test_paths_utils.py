"""Tests for src/agentlint/utils/paths.py."""
from __future__ import annotations

import pytest

from agentlint.utils.paths import SAFE_PATH_PREFIXES, is_safe_path


class TestSafePathPrefixes:
    def test_defaults_include_tmp(self):
        assert "/tmp/" in SAFE_PATH_PREFIXES

    def test_defaults_include_macos_tmpdir(self):
        assert "/var/folders/" in SAFE_PATH_PREFIXES

    def test_defaults_include_private_tmp(self):
        assert "/private/tmp/" in SAFE_PATH_PREFIXES


class TestIsSafePathDefaults:
    def test_path_under_tmp_is_safe(self):
        assert is_safe_path("/tmp/scratch.txt") is True

    def test_path_under_tmp_subdir_is_safe(self):
        assert is_safe_path("/tmp/agentlint-xyz/cache/file.json") is True

    def test_path_under_var_folders_is_safe(self):
        assert is_safe_path("/var/folders/abc/T/xyz/scratch") is True

    def test_path_under_private_tmp_is_safe(self):
        assert is_safe_path("/private/tmp/foo") is True

    def test_path_under_project_dir_is_not_safe(self):
        assert is_safe_path("/Users/x/Projects/foo/secrets.json") is False

    def test_path_under_root_is_not_safe(self):
        assert is_safe_path("/etc/passwd") is False

    def test_relative_path_is_not_safe(self):
        assert is_safe_path("./scratch") is False

    def test_bare_filename_is_not_safe(self):
        assert is_safe_path("scratch.txt") is False

    def test_empty_string_is_not_safe(self):
        assert is_safe_path("") is False

    def test_tmp_without_trailing_slash_does_not_match(self):
        # We require prefix match including trailing slash so "/tmpfoo"
        # does not pass as safe.
        assert is_safe_path("/tmpfoo") is False

    def test_path_named_tmp_inside_project_is_not_safe(self):
        # A directory called "tmp" deep in a project is not /tmp.
        assert is_safe_path("/Users/x/Projects/foo/tmp/bar") is False


class TestIsSafePathExtraPrefixes:
    def test_extra_prefix_recognised(self):
        assert is_safe_path("/scratch/foo", extra_prefixes=["/scratch/"]) is True

    def test_extra_prefix_does_not_replace_defaults(self):
        # Adding a custom prefix must not disable the built-in /tmp.
        assert is_safe_path("/tmp/foo", extra_prefixes=["/scratch/"]) is True

    def test_unmatched_extra_prefix_is_not_safe(self):
        assert is_safe_path("/somewhere/else", extra_prefixes=["/scratch/"]) is False


class TestIsSafePathTmpdirEnv:
    def test_tmpdir_placeholder_resolved(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TMPDIR", "/Users/me/scratch")
        assert (
            is_safe_path(
                "/Users/me/scratch/foo.txt",
                extra_prefixes=["$TMPDIR/"],
            )
            is True
        )

    def test_tmpdir_undefined_skips_placeholder(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TMPDIR", raising=False)
        # With TMPDIR undefined, the placeholder is silently skipped — not an error.
        assert (
            is_safe_path(
                "/anywhere/else",
                extra_prefixes=["$TMPDIR/"],
            )
            is False
        )

    def test_tmpdir_with_trailing_slash_normalised(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setenv("TMPDIR", "/Users/me/scratch/")
        assert (
            is_safe_path(
                "/Users/me/scratch/foo.txt",
                extra_prefixes=["$TMPDIR/"],
            )
            is True
        )
