from __future__ import annotations

import re
import tomllib
from pathlib import Path

import agentlint


def test_package_versions_and_canonical_urls_are_consistent() -> None:
    root = Path(__file__).parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert metadata["version"] == agentlint.__version__
    assert metadata["name"] == "agentlint"
    assert metadata["urls"]["Repository"] == "https://github.com/mauhpr/agentlint"
    assert metadata["urls"]["Issues"].endswith("/agentlint/issues")


def test_release_workflows_verify_once_then_use_oidc_publish_jobs() -> None:
    root = Path(__file__).parents[1]
    production = (root / ".github/workflows/publish.yml").read_text(encoding="utf-8")
    test = (root / ".github/workflows/test-publish.yml").read_text(encoding="utf-8")

    for workflow in (production, test):
        assert "id-token: write" in workflow
        assert "password:" not in workflow
        assert "needs: build" in workflow
        assert "uv run pytest -q" in workflow
        assert "uv build" in workflow
        assert "pypa/gh-action-pypi-publish@" in workflow
    assert "uv lock --check" in production
    assert "uv run ruff check ." in production
    assert "environment:\n      name: pypi" in production
    assert "environment:\n      name: testpypi" in test


def test_workflow_actions_are_immutable_and_checkouts_drop_credentials() -> None:
    root = Path(__file__).parents[1]
    action_ref = re.compile(r"^\s*-\s+uses:\s+\S+@([^\s#]+)", re.MULTILINE)

    for workflow_path in (root / ".github/workflows").glob("*.yml"):
        workflow = workflow_path.read_text(encoding="utf-8")
        refs = action_ref.findall(workflow)
        assert refs, f"{workflow_path.name} contains no actions"
        assert all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in refs)
        assert workflow.count("actions/checkout@") == workflow.count("persist-credentials: false")
