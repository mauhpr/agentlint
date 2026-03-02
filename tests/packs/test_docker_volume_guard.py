"""Tests for docker-volume-guard rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.docker_volume_guard import DockerVolumeGuard


def _ctx(command: str) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
    )


class TestDockerVolumeGuard:
    rule = DockerVolumeGuard()

    # --- Volume deletion — WARNING ---

    def test_docker_volume_rm(self):
        ctx = _ctx("docker volume rm mydb-data")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_docker_volume_remove(self):
        ctx = _ctx("docker volume remove mydb-data")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_docker_volume_prune(self):
        ctx = _ctx("docker volume prune")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_docker_volume_ls_passes(self):
        ctx = _ctx("docker volume ls")
        assert self.rule.evaluate(ctx) == []

    # --- Force remove containers — WARNING ---

    def test_docker_rm_force(self):
        ctx = _ctx("docker rm -f mycontainer")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_docker_container_rm_force(self):
        ctx = _ctx("docker container rm --force mycontainer")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_docker_rm_without_force_passes(self):
        ctx = _ctx("docker rm stopped-container")
        assert self.rule.evaluate(ctx) == []

    # --- Privileged containers — ERROR ---

    def test_docker_run_privileged(self):
        ctx = _ctx("docker run --privileged myimage")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_docker_run_pid_host(self):
        ctx = _ctx("docker run --pid=host myimage")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_docker_run_docker_sock_mount(self):
        ctx = _ctx("docker run -v /var/run/docker.sock:/var/run/docker.sock myimage")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_docker_run_root_fs_mount(self):
        ctx = _ctx("docker run -v /:/host myimage")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    # --- Network host — WARNING ---

    def test_docker_run_network_host(self):
        ctx = _ctx("docker run --network=host myimage")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    # --- Safe docker commands pass ---

    def test_docker_run_relative_mount_passes(self):
        ctx = _ctx("docker run -v ./data:/data myimage")
        assert self.rule.evaluate(ctx) == []

    def test_docker_run_normal_passes(self):
        ctx = _ctx("docker run -p 8080:80 nginx")
        assert self.rule.evaluate(ctx) == []

    def test_docker_ps_passes(self):
        ctx = _ctx("docker ps")
        assert self.rule.evaluate(ctx) == []

    def test_docker_build_passes(self):
        ctx = _ctx("docker build -t myimage .")
        assert self.rule.evaluate(ctx) == []

    # --- allowed_ops config bypass ---

    def test_allowed_ops_bypasses_volume_rm(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "docker volume rm mydb-data"},
            project_dir="/tmp",
            config={"docker-volume-guard": {"allowed_ops": ["docker volume rm (permanent data loss)"]}},
        )
        assert self.rule.evaluate(ctx) == []

    def test_allowed_ops_does_not_bypass_other_operations(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "docker volume prune"},
            project_dir="/tmp",
            config={"docker-volume-guard": {"allowed_ops": ["docker volume rm (permanent data loss)"]}},
        )
        assert len(self.rule.evaluate(ctx)) == 1

    # --- Non-Bash tools ignored ---

    def test_non_bash_tool_ignored(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "script.sh", "content": "docker run --privileged myimage"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []
