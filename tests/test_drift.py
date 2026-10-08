"""Configuration drift: explicit packs that no longer match the repository."""

from __future__ import annotations

import json

from click.testing import CliRunner

from agentlint.cli import main
from agentlint.config import load_config
from agentlint.detector import detect_drift


def _repo(tmp_path, config: str):
    (tmp_path / "agentlint.yml").write_text(config)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    web = tmp_path / "web"
    (web / "src").mkdir(parents=True)
    (web / "package.json").write_text(json.dumps({"dependencies": {"react": "18"}}))
    (web / "src" / "App.tsx").write_text("export default 1\n")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "package.json").write_text("{}")
    return tmp_path


def test_python_only_config_with_frontend_code_drifts(tmp_path):
    repo = _repo(tmp_path, "# Python-only project\npacks: [universal, python]\n")
    drift = {d["pack"]: d["evidence"] for d in detect_drift(load_config(str(repo)), str(repo))}
    assert drift["frontend"] == ["web/package.json", "1 .tsx/.jsx/.vue/.svelte file(s)"]
    assert drift["react"] == ["web/package.json"]
    assert "python" not in drift


def test_auto_detection_ignore_list_and_projects_mapping_do_not_drift(tmp_path):
    repo = _repo(tmp_path, "packs: [universal, python]\ndrift_ignore_packs: [frontend, react]\n")
    assert detect_drift(load_config(str(repo)), str(repo)) == []
    (repo / "agentlint.yml").write_text("stack: auto\n")
    assert detect_drift(load_config(str(repo)), str(repo)) == []
    (repo / "agentlint.yml").write_text(
        "packs: [universal, python]\nprojects:\n  web/:\n    packs: [universal, frontend, react]\n"
    )
    drift = detect_drift(load_config(str(repo)), str(repo))
    assert drift == [{"pack": "frontend", "evidence": ["1 .tsx/.jsx/.vue/.svelte file(s)"]}]


def test_workspace_baseline_is_not_judged_for_drift(tmp_path, monkeypatch):
    repo = _repo(tmp_path, "workspace:\n  required_rules: []\npacks: [universal]\n")
    monkeypatch.setenv("AGENTLINT_WORKSPACE_CONFIG", str(repo / "agentlint.yml"))
    assert detect_drift(load_config(str(repo)), str(repo)) == []


def test_status_and_doctor_surface_drift(tmp_path):
    repo = _repo(
        tmp_path,
        "packs: [universal, python]\nrules:\n  no-destructive-commands:\n    allow_patterns: ['2>&1']\n",
    )
    status = CliRunner().invoke(main, ["status", "--project-dir", str(repo)]).output
    assert "! Drift: 'frontend' pack is not enabled" in status
    # (With no hooks installed, the hook repair step takes priority as "Next:".)
    data = json.loads(
        CliRunner().invoke(main, ["status", "--json", "--project-dir", str(repo)]).output
    )
    assert {d["pack"] for d in data["policy"]["drift"]} == {"frontend", "react"}
    doctor = CliRunner().invoke(main, ["doctor", "--project-dir", str(repo)]).output
    assert "!!  Pack drift: 'frontend'" in doctor
    assert "allow_patterns exempt the whole command" in doctor


def test_nested_worktrees_and_repos_are_not_evidence(tmp_path):
    (tmp_path / "agentlint.yml").write_text("packs: [universal, python]\n")
    for nested in (".worktrees/feat/ui", "vendored/ui"):
        (tmp_path / nested).mkdir(parents=True)
        (tmp_path / nested / "package.json").write_text("{}")
    (tmp_path / "vendored" / ".git").write_text("gitdir: elsewhere\n")
    assert detect_drift(load_config(str(tmp_path)), str(tmp_path)) == []
