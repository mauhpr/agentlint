"""Tests for remote-boot-partition-guard rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.remote_boot_partition_guard import RemoteBootPartitionGuard


def _ctx(command: str) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
        config={},
    )


class TestRemoteBootPartitionGuard:
    rule = RemoteBootPartitionGuard()

    # --- rm targeting boot files ---

    def test_rm_boot_vmlinuz(self):
        ctx = _ctx("rm /boot/vmlinuz-5.10.0-amd64")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR
        assert "vmlinuz" in violations[0].message

    def test_rm_mnt_boot_vmlinuz(self):
        ctx = _ctx("rm /mnt/boot/vmlinuz-5.10.0-amd64")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_rm_target_boot_vmlinuz(self):
        ctx = _ctx("rm /target/boot/vmlinuz-5.10.0-amd64")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_rm_boot_initrd(self):
        ctx = _ctx("rm /boot/initrd.img-5.10.0-amd64")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "initrd" in violations[0].message

    def test_rm_mnt_boot_initrd(self):
        ctx = _ctx("rm /mnt/boot/initrd.img-5.10.0")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_rm_boot_grub(self):
        ctx = _ctx("rm -rf /boot/grub/grub.cfg")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "grub" in violations[0].message

    def test_rm_mnt_boot_grub(self):
        ctx = _ctx("rm /mnt/boot/grub/grubenv")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_rm_target_boot_grub(self):
        ctx = _ctx("rm -rf /target/boot/grub/")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    # --- dd targeting boot partition ---

    def test_dd_of_boot(self):
        ctx = _ctx("dd if=/dev/zero of=/boot/test bs=512 count=1")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "dd" in violations[0].message

    def test_dd_of_mnt_boot(self):
        ctx = _ctx("dd if=/dev/sda1 of=/mnt/boot/backup bs=4M")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    # --- Safe commands ---

    def test_ls_boot_passes(self):
        ctx = _ctx("ls -la /boot/")
        assert self.rule.evaluate(ctx) == []

    def test_cat_boot_vmlinuz_passes(self):
        ctx = _ctx("file /boot/vmlinuz-5.10.0-amd64")
        assert self.rule.evaluate(ctx) == []

    def test_rm_tmp_passes(self):
        ctx = _ctx("rm -rf /tmp/junk")
        assert self.rule.evaluate(ctx) == []

    def test_cp_boot_passes(self):
        ctx = _ctx("cp /boot/vmlinuz-5.10.0 /backup/")
        assert self.rule.evaluate(ctx) == []

    # --- Edge cases ---

    def test_empty_command_passes(self):
        ctx = _ctx("")
        assert self.rule.evaluate(ctx) == []

    # --- Non-Bash tool ignored ---

    def test_non_bash_tool_ignored(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "script.sh", "content": "rm /boot/vmlinuz"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []

    # --- No config bypass (always block) ---

    def test_suggestion_warns_no_proceed(self):
        ctx = _ctx("rm /boot/vmlinuz-5.10.0")
        violations = self.rule.evaluate(ctx)
        assert "Do NOT proceed" in violations[0].suggestion
