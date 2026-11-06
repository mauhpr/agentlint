"""Inconclusive validation must retain clear diagnostics and existing safeguards."""

from __future__ import annotations

import pytest

from agentlint.adapters.codex_patch import PatchError, patch_contexts
from agentlint.formats.plain_json import PlainJsonFormatter
from agentlint.models import AgentEvent, HookEvent, RuleContext
from agentlint.packs.quality.no_dead_imports import NoDeadImports
from agentlint.packs.security.no_bash_file_write import NoBashFileWrite


@pytest.mark.parametrize("content", ["from routers import (", "from routers import *\n"])
def test_incomplete_or_wildcard_imports_do_not_produce_false_unused_names(content):
    context = RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": "/project/app.py"},
        project_dir="/project",
        file_content=content,
        config={"no-dead-imports": {"grace_period": False}},
    )
    assert NoDeadImports().evaluate(context) == []


def test_formatter_without_context_support_preserves_existing_denial():
    class NoStartupContext(PlainJsonFormatter):
        def format(self, violations, event=""):
            return None if event == AgentEvent.SESSION_START else super().format(violations, event)

    original = '{"blocked":true,"violations":[]}'
    assert (
        NoStartupContext().add_activity_context(
            original, AgentEvent.SESSION_START, "pending request"
        )
        == original
    )


def test_oversized_python_source_is_unknown_and_stays_blocked():
    code = "print(" + " " * 65537 + "1)"
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "python - <<'PY'\n" + code + "\nPY"},
        project_dir="/project",
    )
    [violation] = NoBashFileWrite().evaluate(context)
    assert "Cannot classify oversized Python source safely" in violation.message
    assert violation.line is None
    assert "Confirmed" not in violation.message


def test_nonscratch_patch_boundary_keeps_project_containment_guidance(tmp_path):
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="apply_patch",
        tool_input={
            "command": "*** Begin Patch\n*** Add File: /etc/external.py\n+data\n*** End Patch"
        },
        project_dir=str(tmp_path),
    )
    with pytest.raises(PatchError) as error:
        patch_contexts(context)
    correction = error.value.correction()
    assert error.value.reason == "boundary"
    assert "inspection boundary" in correction and "scratch file" not in correction
