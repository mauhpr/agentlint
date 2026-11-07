"""Scratch creation guidance must preserve the patch inspection boundary."""

from __future__ import annotations

import pytest

from agentlint.adapters.codex_patch import PatchError, patch_contexts
from agentlint.models import HookEvent, RuleContext
from agentlint.packs.security.no_bash_file_write import NoBashFileWrite


@pytest.mark.parametrize("label", ["commit ", 'BASE_COMMIT = "', "git_sha: ", "git show "])
def test_excerpt_preserves_typed_git_object_ids(label):
    from agentlint.adapters.codex_patch import _excerpt

    sha = "abcdef0123456789" * 2 + "abcdef01"
    assert sha in _excerpt(label + sha)
    assert sha not in _excerpt("token" + "=" + sha)
    assert sha not in _excerpt(sha)
    assert sha not in _excerpt("password" + "=" + repr("several words commit " + sha))


@pytest.mark.parametrize("path", ["/tmp/diagnostic.txt", "/private/tmp/diagnostic.txt"])
def test_scratch_creation_explains_shell_alternative_without_expanding_patch_scope(tmp_path, path):
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="apply_patch",
        tool_input={"command": f"*** Begin Patch\n*** Add File: {path}\n+data\n*** End Patch"},
        project_dir=str(tmp_path),
    )
    with pytest.raises(PatchError) as error:
        patch_contexts(context)
    assert error.value.reason == "boundary"
    correction = error.value.correction()
    assert "scratch" in correction
    assert "shell" in correction
    assert "inspection boundary" in correction
    context.tool_name = "Bash"
    context.tool_input = {"command": f"printf '%s' data > {path}"}
    assert NoBashFileWrite().evaluate(context) == []
