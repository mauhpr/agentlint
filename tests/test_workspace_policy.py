from __future__ import annotations

import json

import pytest
import yaml
from click.testing import CliRunner

from agentlint.cli import main
from agentlint.config import load_config
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext
from agentlint.packs import load_project_rules


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    policy = root / "agentlint.yml"
    policy.write_text(
        yaml.safe_dump(
            {
                "packs": ["universal", "autopilot"],
                "workspace": {"required_rules": ["no-secrets", "no-force-push"]},
                "rules": {"max-file-size": {"limit": 600}},
            }
        )
    )
    monkeypatch.setenv("AGENTLINT_WORKSPACE_CONFIG", str(policy))
    repo = root / "repo"
    repo.mkdir()
    return root, repo


def test_compose_additive_packs_and_repository_exceptions(workspace):
    root, repo = workspace
    (repo / "agentlint.yml").write_text(
        yaml.safe_dump(
            {
                "packs": ["python"],
                "custom_rules_dir": "rules",
                "rules": {"no-secrets": {"enabled": False, "allow_paths": ["fixture.py"]}},
                "recording": {"enabled": True},
            }
        )
    )
    nested = repo / "src"
    nested.mkdir()
    config = load_config(str(nested))
    assert config.packs == ["universal", "autopilot", "python"]
    assert config.rules["no-secrets"] == {"enabled": True, "allow_paths": ["fixture.py"]}
    assert config.rules["max-file-size"]["limit"] == 600
    assert config.custom_rules_dir == str(repo / "rules")
    assert config.recording == {"enabled": True}
    assert config.required_rules == ["no-secrets", "no-force-push"]


def test_required_rule_survives_pack_mapping_and_repeated_attempts(workspace):
    _, repo = workspace
    (repo / "agentlint.yml").write_text(
        yaml.safe_dump(
            {
                "severity": "relaxed",
                "packs": ["python"],
                "rules": {"no-force-push": False},
                "circuit_breaker": {"enabled": True, "degraded_after": 1, "open_after": 2},
            }
        )
    )
    config = load_config(str(repo))
    engine = Engine(config.with_packs(["python"]), load_project_rules(config, str(repo)))
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "git push origin main --force"},
        project_dir=str(repo),
        config=config.rules,
        session_state={},
    )
    for _ in range(12):
        result = engine.evaluate(context)
        assert result.is_blocking
        assert any(v.rule_id == "no-force-push" for v in result.violations)


def test_protected_inline_and_global_ignores_cannot_hide_secret(workspace):
    _, repo = workspace
    (repo / "agentlint.yml").write_text(
        yaml.safe_dump(
            {
                "rules": {"ignore_paths": ["*"], "allow_paths": ["*"]},
            }
        )
    )
    payload = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(repo / "config.py"),
            "content": '# agentlint:ignore-file\nAPI_KEY = "sk_live_abc123def456ghi789"\n',
        },
    }
    result = CliRunner().invoke(
        main,
        ["check", "--event", "PreToolUse", "--project-dir", str(repo)],
        input=json.dumps(payload),
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("path", ["fixture.py", "tests/fixtures/sample.py"])
def test_explicit_per_rule_fixture_exception_is_preserved(workspace, path):
    _, repo = workspace
    (repo / "agentlint.yml").write_text(
        yaml.safe_dump(
            {
                "rules": {"no-secrets": {"allow_paths": [path]}},
            }
        )
    )
    config = load_config(str(repo))
    context = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        tool_input={
            "file_path": str(repo / path),
            "content": 'API_KEY = "sk_live_abc123def456ghi789"',
        },
        project_dir=str(repo),
        config=config.rules,
    )
    assert not Engine(config, load_project_rules(config, str(repo))).evaluate(context).is_blocking


def test_fallback_outside_scope_and_invalid_workspace(workspace, tmp_path):
    root, repo = workspace
    assert "autopilot" in load_config(str(repo)).packs
    outside = tmp_path / "outside"
    outside.mkdir()
    assert load_config(str(outside)).required_rules == []
    (root / "agentlint.yml").write_text("workspace: {required_rules: [unknown-rule]}\n")
    with pytest.raises(ValueError, match="unknown"):
        load_config(str(repo))


@pytest.mark.parametrize(
    "content", ["[", "[]", "workspace: []", "workspace: {required_rules: bad}"]
)
def test_invalid_workspace_fails_closed_for_native_hook(workspace, content):
    root, repo = workspace
    (root / "agentlint.yml").write_text(content)
    result = CliRunner().invoke(
        main,
        ["check", "--adapter", "codex", "--event", "PreToolUse", "--project-dir", str(repo)],
        input="{}",
    )
    assert result.exit_code == 2
    assert "configuration error" in result.output


def test_strict_default_inherited_and_repo_severity_explicit(workspace):
    root, repo = workspace
    (root / "agentlint.yml").write_text("workspace: {required_rules: []}\nseverity: strict\n")
    (repo / "agentlint.yml").write_text("packs: [python]\n")
    assert load_config(str(repo)).severity == "strict"
    (repo / "agentlint.yml").write_text("severity: standard\n")
    assert load_config(str(repo)).severity == "standard"


def test_invalid_local_yaml_fails_closed(workspace):
    _, repo = workspace
    (repo / "agentlint.yml").write_text("rules: [\n")
    with pytest.raises(ValueError, match="Invalid"):
        load_config(str(repo))


def test_missing_and_shadowed_workspace(workspace, monkeypatch):
    root, repo = workspace
    monkeypatch.setenv("AGENTLINT_WORKSPACE_CONFIG", str(root / "absent.yml"))
    with pytest.raises(ValueError, match="existing"):
        load_config(str(repo))
    second = root / "agentlint.yaml"
    second.write_text("workspace: {required_rules: []}")
    monkeypatch.setenv("AGENTLINT_WORKSPACE_CONFIG", str(second))
    with pytest.raises(ValueError, match="shadowed"):
        load_config(str(repo))


def test_root_custom_rules_keep_their_directory(workspace):
    root, repo = workspace
    (root / "agentlint.yml").write_text(
        "workspace: {required_rules: []}\ncustom_rules_dir: rules\n"
    )
    (repo / "agentlint.yml").write_text("packs: [python]\n")
    assert load_config(str(repo)).custom_rules_dir == str(root / "rules")
