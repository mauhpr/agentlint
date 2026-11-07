"""Relocation evidence must come from the complete inspected patch."""

import pytest

from agentlint.adapters.codex_patch import patch_contexts
from agentlint.models import HookEvent, RuleContext
from agentlint.packs.quality.no_error_handling_removal import NoErrorHandlingRemoval


@pytest.mark.parametrize("preserved", [True, False])
def test_patch_supplies_verified_helper_contents_without_writing_files(tmp_path, preserved):
    before = "def run(result):\n    if result is not None:\n        process(result)\n"
    after = "from .guards import check\ndef run(result):\n    check(result)\n"
    helper = (
        "def check(result):\n    if result is not None:\n        process(result)\n"
        if preserved
        else "def check(result):\n    process(result)\n"
    )
    source = tmp_path / "app.py"
    source.write_text(before)
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: app.py",
            "@@",
            *("-" + line for line in before.splitlines()),
            *("+" + line for line in after.splitlines()),
            "*** Add File: guards.py",
            *("+" + line for line in helper.splitlines()),
            "*** End Patch",
        ]
    )
    contexts = patch_contexts(
        RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="apply_patch",
            tool_input={"command": patch},
            project_dir=str(tmp_path),
        )
    )
    assert bool(NoErrorHandlingRemoval().evaluate(contexts[0])) is not preserved
    assert source.read_text() == before
    assert not (tmp_path / "guards.py").exists()
