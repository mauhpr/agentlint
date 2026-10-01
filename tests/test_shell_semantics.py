from __future__ import annotations

import pytest

from agentlint.config import AgentLintConfig
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs import load_rules
from agentlint.packs.autopilot.production_guard import ProductionGuard
from agentlint.utils.shell import is_readonly_cloud_command, mutation_command, simple_words


def evaluate(command):
    config = AgentLintConfig(packs=["universal", "security", "autopilot"])
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/project",
    )
    return Engine(config, load_rules(config.packs)).evaluate(context)


@pytest.mark.parametrize(
    "command",
    [
        "printf '%s' 'git push --force origin main'",
        "echo 'DROP DATABASE example'",
        "printf '%s' 'gcloud sql instances delete example'",
        "echo 'terraform destroy'",
    ],
)
def test_literal_display_data_does_not_trigger_mutation_rules(command):
    assert not evaluate(command).is_blocking


@pytest.mark.parametrize(
    "command",
    [
        "git push --force origin main",
        "echo $(git push --force origin main)",
        "printf '%s' `git push --force origin main`",
        "echo safe; git push --force origin main",
        "echo 'git push --force origin main' | bash",
        "bash -c 'git push --force origin main'",
        "ssh server 'gcloud sql instances delete example'",
        "python -c 'import os; os.system(\"git push --force origin main\")'",
    ],
)
def test_executable_mutations_remain_visible(command):
    assert evaluate(command).is_blocking
    assert mutation_command(command) == command


def test_literal_output_to_file_still_checked():
    assert evaluate("echo 'plain' > src/example.py").is_blocking
    assert evaluate("echo API_KEY=sk_live_abc123def456ghi789").is_blocking


@pytest.mark.parametrize(
    "command",
    [
        "gcloud run services describe api --project=example-prod --region us-central1",
        "gcloud --project example-prod scheduler jobs list --format=json",
        "gcloud run jobs executions list --project example-prod",
        "aws --profile prod sts get-caller-identity",
    ],
)
def test_narrow_cloud_reads_do_not_require_mutation_permission(command):
    assert is_readonly_cloud_command(command)
    result = evaluate(command)
    assert not any(v.rule_id == "production-guard" for v in result.violations)


@pytest.mark.parametrize(
    "command",
    [
        "gcloud run services update api --project=example-prod",
        "gcloud run services describe api --project=example-prod; gcloud run services update api",
        "gcloud run services describe $(gcloud run services update api) --project=example-prod",
        "gcloud run services describe api --project example-prod --flags-file=unsafe.yaml",
        "gcloud run services describe api --project",
        "gcloud run services describe api --project=",
        "gcloud run services describe api --project --region us-east1",
        "psql -h prod-db -c 'SELECT 1'",  # SQL/interpreter bodies are not inferred safe.
    ],
)
def test_unrecognized_or_compound_forms_are_not_readonly(command):
    assert not is_readonly_cloud_command(command)


@pytest.mark.parametrize(
    "command",
    ["echo 'unterminated", "echo x\nother", "echo x\x00", "", "echo '|'", "echo data > file"],
)
def test_uncertain_syntax_is_kept(command):
    assert mutation_command(command) == command


def test_known_false_positive_fix_does_not_change_organization_rule_input():
    class OrganizationRule(ProductionGuard):
        locked = True

        def evaluate(self, context):
            assert "gcloud" in context.command
            return super().evaluate(context)

    command = "echo 'gcloud run services update api --project example-prod'"
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/project",
    )
    result = Engine(AgentLintConfig(packs=["autopilot"]), [OrganizationRule()]).evaluate(context)
    assert any(v.severity == Severity.ERROR for v in result.violations)


def test_basic_tokenization():
    assert simple_words('gcloud run services describe "my api"') == [
        "gcloud",
        "run",
        "services",
        "describe",
        "my api",
    ]
