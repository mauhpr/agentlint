"""Tests for ssh-destructive-command-guard rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.ssh_destructive_command_guard import SshDestructiveCommandGuard


def _ctx(command: str, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
        config=config or {},
    )


class TestSshDestructiveCommandGuard:
    rule = SshDestructiveCommandGuard()

    # --- Destructive patterns via SSH ---

    def test_ssh_rm_rf(self):
        ctx = _ctx("ssh root@server rm -rf /var/data")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING
        assert "rm -rf" in violations[0].message

    def test_ssh_rm_r(self):
        ctx = _ctx("ssh root@server rm -r /tmp/old")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ssh_dpkg_purge(self):
        ctx = _ctx("ssh root@server dpkg --purge nginx")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "dpkg --purge" in violations[0].message

    def test_ssh_apt_purge(self):
        ctx = _ctx("ssh root@server apt purge nginx")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ssh_apt_remove(self):
        ctx = _ctx("ssh user@host apt remove apache2")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ssh_mkfs(self):
        ctx = _ctx("ssh root@server mkfs.ext4 /dev/sda1")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR
        assert "mkfs" in violations[0].message

    def test_ssh_dd(self):
        ctx = _ctx("ssh root@server dd if=/dev/zero of=/dev/sda bs=512 count=1")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR
        assert "dd" in violations[0].message

    def test_ssh_systemctl_stop(self):
        ctx = _ctx("ssh root@server systemctl stop nginx")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ssh_systemctl_disable(self):
        ctx = _ctx("ssh root@server systemctl disable sshd")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ssh_reboot(self):
        ctx = _ctx("ssh root@server reboot")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ssh_shutdown(self):
        ctx = _ctx("ssh root@server shutdown -h now")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ssh_poweroff(self):
        ctx = _ctx("ssh root@server poweroff")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ssh_halt(self):
        ctx = _ctx("ssh root@server halt")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ssh_kill_9(self):
        ctx = _ctx("ssh root@server kill -9 1234")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ssh_killall(self):
        ctx = _ctx("ssh root@server killall nginx")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ssh_iptables_flush(self):
        ctx = _ctx("ssh root@server iptables -F")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_ssh_terraform_destroy(self):
        ctx = _ctx("ssh deploy@ci terraform destroy -auto-approve")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    # --- No SSH prefix → safe ---

    def test_local_rm_rf_passes(self):
        ctx = _ctx("rm -rf /tmp/junk")
        assert self.rule.evaluate(ctx) == []

    def test_local_reboot_passes(self):
        ctx = _ctx("reboot")
        assert self.rule.evaluate(ctx) == []

    # --- Safe SSH commands ---

    def test_ssh_ls_passes(self):
        ctx = _ctx("ssh root@server ls -la /var")
        assert self.rule.evaluate(ctx) == []

    def test_ssh_cat_passes(self):
        ctx = _ctx("ssh root@server cat /etc/hostname")
        assert self.rule.evaluate(ctx) == []

    # --- Config bypass ---

    def test_allowed_ops_bypasses(self):
        ctx = _ctx(
            "ssh root@server reboot",
            config={"ssh-destructive-command-guard": {"allowed_ops": ["reboot"]}},
        )
        assert self.rule.evaluate(ctx) == []

    def test_allowed_ops_partial_no_bypass(self):
        ctx = _ctx(
            "ssh root@server reboot",
            config={"ssh-destructive-command-guard": {"allowed_ops": ["shutdown"]}},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Non-Bash tool ignored ---

    def test_non_bash_tool_ignored(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "script.sh", "content": "ssh root@server rm -rf /"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []

    # --- Edge cases ---

    def test_empty_command_passes(self):
        ctx = _ctx("")
        assert self.rule.evaluate(ctx) == []

    def test_ssh_rebootstrap_does_not_match(self):
        ctx = _ctx("ssh root@server rebootstrap --config /etc/bootstrap.conf")
        assert self.rule.evaluate(ctx) == []

    def test_ssh_rm_recursive_long_flag(self):
        ctx = _ctx("ssh root@server rm --recursive /var/data")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    # --- Suggestion content ---

    def test_suggestion_mentions_config(self):
        ctx = _ctx("ssh root@server rm -rf /data")
        violations = self.rule.evaluate(ctx)
        assert "allowed_ops" in violations[0].suggestion
