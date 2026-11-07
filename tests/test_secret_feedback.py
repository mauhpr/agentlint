"""Introduced findings and narrow grants must not suppress adjacent credentials."""

import json

from agentlint.approvals import create_grant
from agentlint.config import AgentLintConfig
from agentlint.engine import Engine
from agentlint.formats.plain_json import PlainJsonFormatter
from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.universal.no_secrets import NoSecrets


def assignment(name, value):
    return name + " = " + repr(value) + "\n"


def test_public_detector_prefix_literal_is_not_a_credential(tmp_path):
    prefix = "sk_" + "live_"
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": str(tmp_path / "patterns.py"), "content": repr(prefix)},
        project_dir=str(tmp_path),
    )
    assert NoSecrets().evaluate(context) == []


def test_artifact_findings_ignore_formatting_but_state_changes_are_new(tmp_path):
    for artifact in (
        dict(type="service_account"),
        dict(serial=1, lineage="state-id", resources=[]),
    ):
        before = json.dumps(artifact)
        after = "\n" + json.dumps(artifact, indent=2) + "\n"
        context = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Edit",
            tool_input={"file_path": str(tmp_path / "artifact.json"), "content": after},
            file_content_before=before,
            project_dir=str(tmp_path),
        )
        assert NoSecrets().evaluate(context) == []
    context.tool_input["content"] = json.dumps(dict(serial=2, lineage="state-id", resources=[1]))
    assert NoSecrets().evaluate(context)


def test_finding_approval_relaxes_one_finding_and_is_visible(tmp_path):
    source = tmp_path / "settings.py"
    content = assignment("SERVICE_AUTH_TOKEN", "a1b2c3d4e5f6g7h8")
    content += assignment("OTHER_AUTH_TOKEN", "q1w2e3r4t5y6u7i8")
    source.write_text(content)
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": str(source), "content": content},
        project_dir=str(tmp_path),
    )
    rule = NoSecrets()
    findings = rule.evaluate(context)
    assert len(findings) == 2
    create_grant(
        "secret-finding",
        repository=str(tmp_path),
        reason="reviewed synthetic identifier",
        file_path=str(source),
        rule_id=rule.id,
        finding_id=findings[0].finding_id,
    )
    result = Engine(AgentLintConfig(packs=["universal"]), [rule]).evaluate(context)
    assert [v.severity for v in result.violations] == [Severity.WARNING, Severity.ERROR]
    assert findings[0].finding_id in "\n".join(
        PlainJsonFormatter()._detail_lines(result.violations[0])
    )
    config = AgentLintConfig(packs=["universal"], required_rules=[rule.id])
    assert all(
        v.severity == Severity.ERROR for v in Engine(config, [rule]).evaluate(context).violations
    )


def test_changed_secret_or_extra_occurrence_is_still_introduced(tmp_path):
    prefix = "gh" + "p_"
    before = assignment("value", prefix + "abcdef1234567890")
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Edit",
        tool_input={"file_path": str(tmp_path / "app.py"), "content": before + before},
        file_content_before=before,
        project_dir=str(tmp_path),
    )
    rule = NoSecrets()
    assert len(rule.evaluate(context)) == 1
    context.tool_input["content"] = assignment("value", prefix + "changed1234567890")
    assert len(rule.evaluate(context)) == 1
    context.tool_name = "Write"
    context.tool_input["content"] = before
    assert len(rule.evaluate(context)) == 1  # full writes remain full scans
