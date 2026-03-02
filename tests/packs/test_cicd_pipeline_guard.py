"""Tests for cicd-pipeline-guard rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.universal.cicd_pipeline_guard import CicdPipelineGuard


def _ctx(
    tool_name: str,
    file_path: str,
    session_state: dict | None = None,
    config: dict | None = None,
) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input={"file_path": file_path, "content": "# workflow"},
        project_dir="/tmp/project",
        config=config or {},
        session_state=session_state or {},
    )


class TestCicdPipelineGuard:
    rule = CicdPipelineGuard()

    # --- ERROR: CI/CD pipeline files ---

    def test_write_github_workflow_yml(self):
        ctx = _ctx("Write", ".github/workflows/deploy.yml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_edit_github_workflow_yaml(self):
        ctx = _ctx("Edit", ".github/workflows/ci.yaml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_write_gitlab_ci(self):
        ctx = _ctx("Write", ".gitlab-ci.yml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_write_circleci_config(self):
        ctx = _ctx("Write", ".circleci/config.yml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_write_jenkinsfile(self):
        ctx = _ctx("Write", "Jenkinsfile")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_write_jenkinsfile_variant(self):
        ctx = _ctx("Write", "Jenkinsfile.prod")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_write_azure_pipelines(self):
        ctx = _ctx("Write", "azure-pipelines.yml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_write_travis_yml(self):
        ctx = _ctx("Write", ".travis.yml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_write_cloudbuild_yaml(self):
        ctx = _ctx("Write", "cloudbuild.yaml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_multiedit_github_workflow(self):
        ctx = _ctx("MultiEdit", ".github/workflows/release.yml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- WARNING: build-time files ---

    def test_write_dockerfile(self):
        ctx = _ctx("Write", "Dockerfile")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_write_dockerfile_prod(self):
        ctx = _ctx("Write", "Dockerfile.prod")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_write_docker_compose(self):
        ctx = _ctx("Write", "docker-compose.yml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_write_docker_compose_override(self):
        ctx = _ctx("Write", "docker-compose.override.yaml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    # --- Session-state approval gate ---

    def test_approved_file_exact_match_passes(self):
        ctx = _ctx(
            "Write",
            ".github/workflows/deploy.yml",
            session_state={"approved_cicd_files": [".github/workflows/deploy.yml"]},
        )
        assert self.rule.evaluate(ctx) == []

    def test_approved_file_glob_match_passes(self):
        ctx = _ctx(
            "Write",
            ".github/workflows/deploy.yml",
            session_state={"approved_cicd_files": [".github/workflows/*"]},
        )
        assert self.rule.evaluate(ctx) == []

    def test_different_approved_file_still_blocks(self):
        ctx = _ctx(
            "Write",
            ".github/workflows/release.yml",
            session_state={"approved_cicd_files": [".github/workflows/deploy.yml"]},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Config allowed_files permanent bypass ---

    def test_config_allowed_files_bypasses(self):
        ctx = _ctx(
            "Write",
            ".github/workflows/dev-only.yml",
            config={"cicd-pipeline-guard": {"allowed_files": [".github/workflows/dev-only.yml"]}},
        )
        assert self.rule.evaluate(ctx) == []

    # --- Regular source files pass ---

    def test_write_source_file_passes(self):
        ctx = _ctx("Write", "src/app.py")
        assert self.rule.evaluate(ctx) == []

    def test_write_readme_passes(self):
        ctx = _ctx("Write", "README.md")
        assert self.rule.evaluate(ctx) == []

    def test_write_pyproject_toml_passes(self):
        ctx = _ctx("Write", "pyproject.toml")
        assert self.rule.evaluate(ctx) == []

    # --- Non-file tools ignored ---

    def test_bash_tool_ignored(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "cat .github/workflows/deploy.yml"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []

    # --- Violation details ---

    def test_violation_includes_file_path(self):
        ctx = _ctx("Write", ".github/workflows/deploy.yml")
        violations = self.rule.evaluate(ctx)
        assert violations[0].file_path == ".github/workflows/deploy.yml"

    def test_suggestion_mentions_approved_cicd_files(self):
        ctx = _ctx("Write", ".github/workflows/deploy.yml")
        violations = self.rule.evaluate(ctx)
        assert "approved_cicd_files" in violations[0].suggestion
