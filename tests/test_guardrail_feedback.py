"""End-to-end corrections for the October guardrail usability reports."""

from __future__ import annotations

import pytest

from agentlint.adapters.codex_patch import PatchError, _path, _read, _update
from agentlint.cli import _patch_violation
from agentlint.config import AgentLintConfig
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext
from agentlint.packs import load_rules


def _command_rules(command, state=None):
    config = AgentLintConfig(packs=["universal", "security", "autopilot"])
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/project",
        session_state=state if state is not None else {},
    )
    return {
        v.rule_id for v in Engine(config, load_rules(config.packs)).evaluate(context).violations
    }


@pytest.mark.parametrize(
    "command",
    [
        "wag-context work session update --session-started-at 2026-10-24T10:00:00Z",
        "python workflow.py --profile review --project example",
        "uv run python scripts/workflow.py --profile review --project example",
        'wag-context work session update --note "terraform apply is awaiting review"',
        'wag-context work session update --note "gcloud compute networks delete example"',
    ],
)
def test_metadata_arguments_are_not_executable_operations(command):
    assert not _command_rules(command) & {
        "system-scheduler-guard",
        "cross-account-guard",
        "dry-run-required",
        "cloud-infra-mutation",
    }


@pytest.mark.parametrize(
    "command",
    [
        "terraform apply",
        "command terraform apply",
        "env MODE=dev /usr/bin/terraform apply",
        "uv run --frozen terraform apply",
        "uv run --with helper terraform apply",
        "uv run --with=helper terraform apply",
        "uv run --unknown terraform apply",
        "poetry run terraform apply",
        "npx terraform apply",
        "pnpm exec terraform apply",
        "nice terraform apply",
        "unknown-launcher terraform apply",
        'bash -c "terraform apply"',
        "python3 -c 'import os; os.system(\"terraform apply\")'",
        'wag-context work session update --note "done"; terraform apply',
    ],
)
def test_infrastructure_execution_still_requires_preview(command):
    assert "dry-run-required" in _command_rules(command)


@pytest.mark.parametrize("command", ["uv run --python", "uv run", "env", "command", "npx"])
def test_incomplete_execution_wrappers_do_not_qualify_for_an_exemption(command):
    from agentlint.utils.shell import executable_operations

    assert executable_operations(command, {"terraform"}) is None


@pytest.mark.parametrize(
    "command, blocked",
    [
        ("terraform show 'terraform apply'", False),
        ("terraform apply -var 'note=--dry-run'", True),
        ("terraform apply && terraform plan", True),
        ("terraform plan && terraform apply", False),
        ("'/usr/bin/terraform' apply", True),
    ],
)
def test_preview_detection_uses_the_command_and_real_flags(command, blocked):
    assert ("dry-run-required" in _command_rules(command)) is blocked


def test_local_profiles_do_not_pollute_cloud_account_history():
    from agentlint.packs.autopilot.cross_account_guard import CrossAccountGuard

    rule = CrossAccountGuard()
    state = {}
    for command in ["python workflow.py --profile local", "aws s3 ls --profile staging"]:
        context = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": command},
            project_dir="/project",
            session_state=state,
        )
        assert rule.evaluate(context) == []
    assert state["cross_account"]["seen_aws_profiles"] == ["staging"]


@pytest.mark.parametrize("prefix", ["", "env AWS_PROFILE=dev ", "uv run --frozen "])
def test_real_account_selectors_are_tokenized_and_warn_on_switch(prefix):
    from agentlint.packs.autopilot.cross_account_guard import CrossAccountGuard

    rule = CrossAccountGuard()
    state = {"cross_account": {"seen_aws_profiles": ["dev"], "seen_gcloud_projects": []}}
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": prefix + "aws s3 ls --profile=release"},
        project_dir="/project",
        session_state=state,
    )
    [violation] = rule.evaluate(context)
    assert "dev → release" in violation.message
    assert violation.operation == "aws account selector"


@pytest.mark.parametrize(
    "command",
    [
        "set -o pipefail && pytest -q 2>&1 | tee /private/tmp/test-evidence.log",
        "cat report.json > /private/tmp/report-export.json",
        "cat report.json > review-artifacts/report-export.json",
    ],
)
def test_declared_evidence_destinations_are_allowed_without_disabling_file_write_guard(command):
    from agentlint.packs.security.no_bash_file_write import NoBashFileWrite

    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/project",
        config={"no-bash-file-write": {"allow_paths": ["review-artifacts/*.json"]}},
    )
    rule = NoBashFileWrite()
    assert rule.evaluate(context) == []
    context.tool_input = {"command": "cat report.json > src/report.py"}
    assert rule.evaluate(context)


@pytest.mark.parametrize(
    "command",
    [
        "uv pip install --python .docs-venv/bin/python -r requirements-docs.txt",
        "python3 -m pip install --disable-pip-version-check --requirement requirements-docs.txt",
        "pip install --requirement=requirements-docs.txt",
        "uv pip install --python .docs-venv/bin/python -r 'docs/requirements docs.txt'",
    ],
)
def test_dependency_manifests_are_recognized_after_install_options(command):
    assert "dependency-hygiene" not in _command_rules(command)


def test_requirement_install_does_not_exempt_a_later_ad_hoc_install():
    assert "dependency-hygiene" in _command_rules(
        "pip install -r requirements.txt && pip install extra"
    )


@pytest.mark.parametrize("tool", ["Write", "Edit"])
def test_strict_file_size_check_rejects_threshold_crossing_before_write(tmp_path, tool):
    import json

    from click.testing import CliRunner

    from agentlint.cli import main

    (tmp_path / "agentlint.yml").write_text("packs: [universal]\nseverity: strict\n")
    path = tmp_path / "checkpoint.md"
    before = "existing\n" * 499
    path.write_text(before)
    tool_input = {"file_path": str(path)}
    if tool == "Write":
        tool_input["content"] = before + "new\nnew\n"
    else:
        tool_input.update(old_string="existing\n", new_string="existing\nnew\n", replace_all=True)
    result = CliRunner().invoke(
        main,
        ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
        input=json.dumps({"tool_name": tool, "tool_input": tool_input}),
    )
    decision = json.loads(result.output)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "max-file-size" in decision["permissionDecisionReason"]
    assert path.read_text() == before


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
