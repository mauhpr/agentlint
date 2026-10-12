"""Capture real hook decisions for the illustrated demo; never execute commands."""

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
    config = AgentLintConfig(packs=["universal", "quality", "security"])
    engine = Engine(config, load_rules(config.packs))
    records = []
    for command in (
        "git push --force origin main",
        "git diff --stat",
        "git push origin feature/demo",
    ):
        context = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": command},
            project_dir="/example/project",
            session_state={},
        )
        result = engine.evaluate(context)
        formatted = CodexHookFormatter().format(result.violations, AgentEvent.PRE_TOOL_USE)
        records.append(
            {
                "command": command,
                "blocked": result.is_blocking,
                "rules_evaluated": result.rules_evaluated,
                "violations": [v.to_dict() for v in result.violations],
                "hook_output": json.loads(formatted) if formatted else None,
            }
        )
    assert [record["blocked"] for record in records] == [True, False, False]
    print(
        json.dumps(
            {"agentlint_version": __version__, "commands_executed": False, "examples": records},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
