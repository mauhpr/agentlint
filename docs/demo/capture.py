"""Capture decisions for synthetic operations; never write files or run commands."""

from __future__ import annotations

import json

from agentlint import __version__
from agentlint.config import AgentLintConfig
from agentlint.engine import Engine
from agentlint.formats.codex_hooks import CodexHookFormatter
from agentlint.models import AgentEvent, HookEvent, RuleContext
from agentlint.packs import load_rules


def main() -> None:
    """Print decisions from built-in rules with an isolated standard configuration."""
    config = AgentLintConfig(packs=["universal", "quality"])
    engine = Engine(config, load_rules(config.packs))
    # A non-functional marker exercises the assignment detector in memory.
    # It is omitted from saved evidence and masked in the video.
    synthetic_content = "api_key = " + repr("DEMO_ONLY_NOT_A_REAL_CREDENTIAL")
    corrected_content = 'import os\napi_key = os.environ["PAYMENT_API_KEY"]\n'
    cases = (
        (
            "credential_write",
            "Write",
            {"file_path": "/example/project/config.py", "content": synthetic_content},
        ),
        (
            "corrected_write",
            "Write",
            {"file_path": "/example/project/config.py", "content": corrected_content},
        ),
        ("test_command", "Bash", {"command": "pytest"}),
    )
    records = []
    for label, tool_name, tool_input in cases:
        context = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name=tool_name,
            tool_input=tool_input,
            project_dir="/example/project",
            session_state={},
        )
        result = engine.evaluate(context)
        formatted = CodexHookFormatter().format(result.violations, AgentEvent.PRE_TOOL_USE)
        saved_input = dict(tool_input)
        if label == "credential_write":
            saved_input["content"] = "<synthetic credential assignment redacted>"
        records.append(
            {
                "label": label,
                "event": HookEvent.PRE_TOOL_USE.value,
                "tool_name": tool_name,
                "tool_input": saved_input,
                "content_redacted": label == "credential_write",
                "blocked": result.is_blocking,
                "rules_evaluated": result.rules_evaluated,
                "violations": [v.to_dict() for v in result.violations],
                "hook_output": json.loads(formatted) if formatted else None,
            }
        )
    assert [record["blocked"] for record in records] == [True, False, False]
    assert any(
        violation["rule_id"] == "no-secrets" and violation["severity"] == "error"
        for violation in records[0]["violations"]
    )
    assert records[0]["hook_output"]["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert all(not record["violations"] for record in records[1:])
    print(
        json.dumps(
            {
                "agentlint_version": __version__,
                "commands_executed": False,
                "file_write_operations_executed": False,
                "credential_fixture": "synthetic marker; omitted from saved inputs",
                "packs": config.packs,
                "severity": config.severity,
                "examples": records,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
