"""Tests for package-publish-guard rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.universal.package_publish_guard import PackagePublishGuard


def _ctx(command: str, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
        config=config or {},
    )


class TestPackagePublishGuard:
    rule = PackagePublishGuard()

    # --- npm/yarn/pnpm — ERROR ---

    def test_npm_publish(self):
        ctx = _ctx("npm publish")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_npm_publish_with_tag(self):
        ctx = _ctx("npm publish --tag latest")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_yarn_publish(self):
        ctx = _ctx("yarn publish")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_pnpm_publish(self):
        ctx = _ctx("pnpm publish")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    # --- Python — ERROR ---

    def test_twine_upload(self):
        ctx = _ctx("twine upload dist/*")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_python_m_twine_upload(self):
        ctx = _ctx("python -m twine upload dist/*.whl")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_flit_publish(self):
        ctx = _ctx("flit publish")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_poetry_publish(self):
        ctx = _ctx("poetry publish")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    # --- Ruby — ERROR ---

    def test_gem_push(self):
        ctx = _ctx("gem push my-gem-1.0.gem")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    # --- Rust — ERROR ---

    def test_cargo_publish(self):
        ctx = _ctx("cargo publish")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    # --- Docker — WARNING ---

    def test_docker_push(self):
        ctx = _ctx("docker push myimage:latest")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_docker_push_specific_registry(self):
        ctx = _ctx("docker push gcr.io/myproject/myimage:v1.0")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    # --- Install commands pass through ---

    def test_npm_install_passes(self):
        ctx = _ctx("npm install express")
        assert self.rule.evaluate(ctx) == []

    def test_pip_install_passes(self):
        ctx = _ctx("pip install requests")
        assert self.rule.evaluate(ctx) == []

    def test_gem_install_passes(self):
        ctx = _ctx("gem install rails")
        assert self.rule.evaluate(ctx) == []

    def test_cargo_install_passes(self):
        ctx = _ctx("cargo install ripgrep")
        assert self.rule.evaluate(ctx) == []

    def test_docker_pull_passes(self):
        ctx = _ctx("docker pull nginx:latest")
        assert self.rule.evaluate(ctx) == []

    def test_docker_build_passes(self):
        ctx = _ctx("docker build -t myimage .")
        assert self.rule.evaluate(ctx) == []

    # --- Config allowed_registries bypass ---

    def test_allowed_registry_bypasses(self):
        ctx = _ctx(
            "docker push registry.company.internal/myimage:v1",
            config={"package-publish-guard": {"allowed_registries": ["registry.company.internal"]}},
        )
        assert self.rule.evaluate(ctx) == []

    def test_allowed_registry_does_not_bypass_unrelated_command(self):
        ctx = _ctx(
            "npm publish",
            config={"package-publish-guard": {"allowed_registries": ["registry.company.internal"]}},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Non-Bash tools ignored ---

    def test_non_bash_tool_ignored(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "publish.sh", "content": "npm publish"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []
