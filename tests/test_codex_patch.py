from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from agentlint.adapters.codex_patch import MAX_FILES, PatchError, patch_contexts
from agentlint.cli import main
from agentlint.models import HookEvent, RuleContext


def context(tmp_path, patch, event=HookEvent.PRE_TOOL_USE, state=None):
    return RuleContext(
        event=event,
        tool_name="apply_patch",
        tool_input={"command": patch},
        project_dir=str(tmp_path),
        session_state=state if state is not None else {},
    )


def envelope(body):
    return "*** Begin Patch\n" + body + "\n*** End Patch"


def check(tmp_path, patch, event="PreToolUse"):
    result = CliRunner().invoke(
        main,
        ["check", "--adapter", "codex", "--event", event, "--project-dir", str(tmp_path)],
        input=json.dumps(
            {
                "tool_name": "apply_patch",
                "tool_input": {"command": patch},
            }
        ),
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.output or "{}")


def test_all_files_are_checked_and_no_file_is_written(tmp_path):
    patch = envelope(
        '*** Add File: ok.py\n+x = 1\n*** Add File: config.py\n+API_KEY = "sk_live_abc123def456ghi789"'
    )
    output = check(tmp_path, patch)["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "no-secrets" in output["permissionDecisionReason"]
    assert not (tmp_path / "ok.py").exists()
    assert not (tmp_path / "config.py").exists()


def test_ci_add_delete_and_rename_destination_checked(tmp_path):
    (tmp_path / "source.yml").write_text("name: sample\n")
    patch = envelope(
        "*** Update File: source.yml\n*** Move to: .github/workflows/check.yml\n@@\n-name: sample\n+name: changed"
    )
    assert (
        "cicd-pipeline-guard"
        in check(tmp_path, patch)["hookSpecificOutput"]["permissionDecisionReason"]
    )
    directory = tmp_path / ".github/workflows"
    directory.mkdir(parents=True)
    (directory / "check.yml").write_text("name: check\n")
    patch = envelope("*** Delete File: .github/workflows/check.yml")
    assert (
        "cicd-pipeline-guard"
        in check(tmp_path, patch)["hookSpecificOutput"]["permissionDecisionReason"]
    )
    assert (directory / "check.yml").exists()


def test_update_test_weakening_and_error_handling(tmp_path):
    (tmp_path / "test_example.py").write_text("def test_real():\n    assert value == 3\n")
    patch = envelope(
        "*** Update File: test_example.py\n@@\n-    assert value == 3\n+    assert True"
    )
    assert "no-test-weakening" in check(tmp_path, patch)["hookSpecificOutput"]["additionalContext"]
    (tmp_path / "agentlint.yml").write_text("packs: [universal, quality]\n")
    (tmp_path / "app.py").write_text("try:\n    do_work()\nexcept ValueError:\n    handle()\n")
    patch = envelope(
        "*** Update File: app.py\n@@\n-try:\n-    do_work()\n-except ValueError:\n-    handle()\n+do_work()"
    )
    assert (
        "no-error-handling-removal"
        in check(tmp_path, patch)["hookSpecificOutput"]["additionalContext"]
    )


def test_rename_checks_old_protected_path(tmp_path):
    source = tmp_path / ".github/workflows/ci.yml"
    source.parent.mkdir(parents=True)
    source.write_text("name: ci\n")
    patch = envelope(
        "*** Update File: .github/workflows/ci.yml\n*** Move to: public.yml\n@@\n-name: ci\n+name: renamed"
    )
    assert (
        "cicd-pipeline-guard"
        in check(tmp_path, patch)["hookSpecificOutput"]["permissionDecisionReason"]
    )


def test_multiple_hunks_context_anchor_and_end_of_file(tmp_path):
    (tmp_path / "app.py").write_text("def first():\n    old()\n\ndef second():\n    before()\n")
    patch = envelope(
        "*** Update File: app.py\n@@ def first():\n-    old()\n+    new()\n@@ def second():\n-    before()\n+    after()\n*** End of File"
    )
    translated = patch_contexts(context(tmp_path, patch))
    assert translated[0].file_content == "def first():\n    new()\n\ndef second():\n    after()\n"


def test_post_context_reads_actual_result_and_keeps_before(tmp_path):
    (tmp_path / "x.py").write_text("old\n")
    patch = envelope("*** Update File: x.py\n@@\n-old\n+new")
    state = {}
    patch_contexts(context(tmp_path, patch, state=state))
    (tmp_path / "x.py").write_text("actual\n")
    after = patch_contexts(context(tmp_path, patch, HookEvent.POST_TOOL_USE, state))
    assert after[0].file_content == "actual\n"
    assert after[0].file_content_before == "old\n"


@pytest.mark.parametrize(
    "body",
    [
        "*** Add File: ../outside.py\n+x",
        "*** Add File: .\n+x",
        "*** Unknown File: x\n+x",
        "*** Add File: x\nbad",
        "*** Delete File: x\n+bad",
        "*** Update File: missing\n@@\n-a\n+b",
        "*** Add File: x\n+a\n*** Add File: x\n+b",
    ],
)
def test_invalid_patch_fails_closed(tmp_path, body):
    output = check(tmp_path, envelope(body))["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "codex-patch-inspection" in output["permissionDecisionReason"]


def test_symlink_escape_and_overwrite_are_rejected(tmp_path):
    (tmp_path / "outside").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(PatchError):
        patch_contexts(context(tmp_path, envelope("*** Add File: outside/other\n+x")))
    (tmp_path / "x").write_text("keep\n")
    with pytest.raises(PatchError, match="overwrite"):
        patch_contexts(context(tmp_path, envelope("*** Add File: x\n+replace")))
    (tmp_path / "x2").write_text("preserve\n")
    with pytest.raises(PatchError, match="overwrite"):
        patch_contexts(
            context(tmp_path, envelope("*** Update File: x\n*** Move to: x2\n@@\n-keep\n+new"))
        )


def test_limits_and_invalid_envelope(tmp_path):
    for patch in (None, "invalid", "x" * 2_000_001):
        with pytest.raises(PatchError):
            patch_contexts(context(tmp_path, patch))
    body = "\n".join(f"*** Add File: f{i}\n+x" for i in range(MAX_FILES + 1))
    with pytest.raises(PatchError, match="limit"):
        patch_contexts(context(tmp_path, envelope(body)))


def test_whitespace_matching_append_and_empty_file(tmp_path):
    (tmp_path / "x").write_text("a  \nb\n")
    patch = envelope("*** Update File: x\n@@\n-a\n+A\n@@\n+end")
    assert patch_contexts(context(tmp_path, patch))[0].file_content == "A\nb\nend\n"
    (tmp_path / "empty").write_text("")
    assert (
        patch_contexts(context(tmp_path, envelope("*** Update File: empty")))[0].file_content == ""
    )


@pytest.mark.parametrize(
    "body",
    ["@@\n-missing\n+new", "@@ missing\n-a\n+b", "@@\n?bad", "@@\n a\n*** End of File\n+bad"],
)
def test_invalid_hunks_rejected(tmp_path, body):
    (tmp_path / "x").write_text("a\n")
    with pytest.raises(PatchError):
        patch_contexts(context(tmp_path, envelope("*** Update File: x\n" + body)))


def test_native_session_connects_pre_post_and_stop(tmp_path, monkeypatch):
    import hashlib
    import os

    from agentlint.session import load_session

    identity = "native-session/unsafe-filename"
    key = "codex-" + hashlib.sha256(identity.encode()).hexdigest()
    path = tmp_path / "app.py"
    path.write_text("old\n")
    payload = {
        "cwd": str(tmp_path),
        "session_id": identity,
        "tool_name": "apply_patch",
        "tool_input": {"command": envelope("*** Update File: app.py\n@@\n-old\n+new")},
    }
    runner = CliRunner()
    result = runner.invoke(
        main, ["check", "--adapter", "codex", "--event", "PreToolUse"], input=json.dumps(payload)
    )
    assert result.exit_code == 0, result.output
    assert load_session(key)["file_cache"][str(path)] == "old\n"
    assert "AGENTLINT_SESSION_ID" not in os.environ
    path.write_text("new\n")
    # Hook processes can have different parents; payload identity wins.
    monkeypatch.setattr(os, "getppid", lambda: 987654)
    result = runner.invoke(
        main, ["check", "--adapter", "codex", "--event", "PostToolUse"], input=json.dumps(payload)
    )
    assert result.exit_code == 0, result.output
    assert not load_session(key)["file_cache"]
    assert str(path) in load_session(key)["files_touched"]
    result = runner.invoke(main, ["report", "--adapter", "codex"], input=json.dumps(payload))
    assert result.exit_code == 0, result.output
    assert load_session(key) == {}
    assert "AGENTLINT_SESSION_ID" not in os.environ


def test_native_session_preserves_explicit_key(tmp_path, monkeypatch):
    from agentlint.session import load_session

    monkeypatch.setenv("AGENTLINT_SESSION_ID", "integration-key")
    payload = {
        "cwd": str(tmp_path),
        "session_id": "native",
        "tool_name": "Bash",
        "tool_input": {"command": "pwd"},
    }
    result = CliRunner().invoke(
        main, ["check", "--adapter", "codex", "--event", "PreToolUse"], input=json.dumps(payload)
    )
    assert result.exit_code == 0, result.output
    assert load_session("integration-key")


def test_tool_working_directory_controls_patch_resolution(tmp_path):
    from dataclasses import replace

    subdir = tmp_path / "src"
    subdir.mkdir()
    ctx = replace(
        context(tmp_path, envelope("*** Add File: app.py\n+x = 1")), working_directory=str(subdir)
    )
    assert patch_contexts(ctx)[0].file_path == str(subdir / "app.py")
    with pytest.raises(PatchError, match="working directory"):
        patch_contexts(replace(ctx, working_directory=str(tmp_path.parent)))


def test_oversized_input_file_rejected(tmp_path):
    (tmp_path / "large").write_text("x" * 5_000_001)
    with pytest.raises(PatchError, match="size limit"):
        patch_contexts(context(tmp_path, envelope("*** Delete File: large")))
