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


# --- v2.9.0 parsed operations ------------------------------------------------

from agentlint.utils.shell import split_operations  # noqa: E402


def _rule_ids(command, packs=("universal", "security", "autopilot"), rules=None):
    config = AgentLintConfig(packs=list(packs), rules=rules or {})
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/project",
        config=rules or {},
    )
    return {
        v.rule_id for v in Engine(config, load_rules(config.packs)).evaluate(context).violations
    }


def test_feature_push_then_pr_against_main_is_not_push_to_main():
    """Field regression: `--base main` in a later operation was read as pushing to main."""
    ids = _rule_ids("git push -u origin feat/date-handling && gh pr create --base main --fill")
    assert "no-push-to-main" not in ids
    assert "no-push-to-main" in _rule_ids("git push origin main")
    assert "no-push-to-main" in _rule_ids("git fetch && git push origin main")


def test_force_push_detection_is_per_operation():
    assert "no-force-push" in _rule_ids("git status && git push --force origin main")
    chained = evaluate("git push --force-with-lease origin feat/x && gh pr create --base main")
    alone = evaluate("git push --force-with-lease origin feat/x")
    # The later `--base main` must not upgrade a feature-branch lease push to protected.
    assert [(v.rule_id, v.severity, v.message) for v in chained.violations] == [
        (v.rule_id, v.severity, v.message) for v in alone.violations
    ]
    assert not chained.is_blocking


@pytest.mark.parametrize(
    "command",
    [
        'grep -rn "rm -rf /" logs/',
        "rg 'git push --force origin main' docs",
        'git log --grep "DROP DATABASE"',
        "git log --oneline | grep 'terraform destroy'",
        "sed -n '1,5p' notes/'rm -rf ~'.md",
        "gh pr view 12 && echo 'git push --force origin main'",
        "find . -name '*.py' | head",
    ],
)
def test_quoted_arguments_to_read_only_commands_are_data(command):
    assert not evaluate(command).is_blocking


@pytest.mark.parametrize(
    "command",
    [
        "echo ok && rm -rf ~",
        "grep x f; git push --force origin main",
        "echo '&&' ; rm -rf /",
        "sed -i 's/a/b/' f && rm -rf /",
        "echo 'git push --force origin main' | bash",
        "cat <<EOF | sh\nrm -rf /\nEOF",
        "git push --force origin main # comment",
    ],
)
def test_state_changing_operations_stay_visible(command):
    assert evaluate(command).is_blocking


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("a && b || c ; d | e & f", ["a", "b", "c", "d", "e", "f"]),
        ("uv run pytest -q > /tmp/log 2>&1", ["uv run pytest -q > /tmp/log 2>&1"]),
        ("echo \"a b\" 'c d'", ["echo \"a b\" 'c d'"]),
        ("rm -rf ~/x *.tmp", ["rm -rf ~/x *.tmp"]),
        ("ls # trailing comment", ["ls"]),
        ("a\nb", ["a", "b"]),
    ],
)
def test_split_operations_shapes(command, expected):
    assert [op.text for op in split_operations(command)] == expected


@pytest.mark.parametrize(
    "command",
    [
        "echo $(id)",
        "echo `id`",
        'echo "$HOME"',
        "(cd x && rm -rf y)",
        "cat <<EOF\nx\nEOF",
        "echo 'unterminated",
        'echo "unterminated',
        "ls >",
        "&& ls",
        "ls | bash",
        "trailing \\",
    ],
)
def test_split_operations_rejects_unmodelled_syntax(command):
    assert split_operations(command) is None


def test_classification():
    kinds = {
        op.text: op.kind
        for op in split_operations(
            "git status; git branch -D x; git remote -v; gh pr list; gh pr merge 1; "
            "sed -i s/a/b/ f; env FOO=1 make; cat f > out; cat f > /dev/null; printf x"
        )
    }
    assert kinds["git status"] == "read"
    assert kinds["git branch -D x"] == "mutate"
    assert kinds["git remote -v"] == "read"
    assert kinds["gh pr list"] == "read"
    assert kinds["gh pr merge 1"] == "mutate"
    assert kinds["sed -i s/a/b/ f"] == "mutate"
    assert kinds["env FOO=1 make"] == "mutate"
    assert kinds["cat f > out"] == "mutate"
    assert kinds["cat f > /dev/null"] == "read"
    assert kinds["printf x"] == "display"


def test_allow_operations_exempts_only_the_matching_operation():
    rules = {
        "no-destructive-commands": {
            "allow_operations": [{"binary": "rm", "args_prefix": ["-rf", "build"]}]
        }
    }
    assert "no-destructive-commands" not in _rule_ids("rm -rf build", rules=rules)
    # The allowance cannot exempt another chained operation.
    assert "no-destructive-commands" in _rule_ids("rm -rf build && rm -rf ~", rules=rules)
    regex = {
        "no-destructive-commands": {
            "allow_operations": [{"binary": "rm", "args_regex": r"-rf dist/\S+"}]
        }
    }
    assert "no-destructive-commands" not in _rule_ids("rm -rf dist/pkg", rules=regex)
    assert "no-destructive-commands" in _rule_ids("rm -rf ~", rules=regex)


def test_allow_patterns_still_short_circuit_unparseable_but_not_required(tmp_path):
    config = AgentLintConfig(
        packs=["universal"],
        required_rules=["no-destructive-commands"],
        rules={
            "no-destructive-commands": {
                "allow_operations": [{"binary": "rm", "args_prefix": ["-rf"]}]
            }
        },
    )
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "rm -rf ~"},
        project_dir="/project",
        config=config.rules,
    )
    result = Engine(config, load_rules(config.packs)).evaluate(context)
    assert any(v.rule_id == "no-destructive-commands" for v in result.violations)


@pytest.mark.parametrize(
    "command",
    ["find / -name x -delete", "printf 'rm -rf /' | xargs sh -c", "ls |"],
)
def test_never_weaker_than_raw_matching(command):
    """Commands the parser does not exempt keep their previous (raw) result."""
    ops = split_operations(command)
    assert ops is None or all(op.kind == "mutate" for op in ops if op.binary in {"find"})
