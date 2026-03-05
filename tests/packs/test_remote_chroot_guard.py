"""Tests for remote-chroot-guard rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.remote_chroot_guard import RemoteChrootGuard


def _ctx(command: str, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
        config=config or {},
    )


class TestRemoteChrootGuard:
    rule = RemoteChrootGuard()

    # --- ERROR: bootloader package removal in chroot ---

    def test_chroot_dpkg_purge_grub(self):
        ctx = _ctx("chroot /mnt dpkg --purge grub-efi-amd64")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR
        assert "dpkg --purge" in violations[0].message

    def test_chroot_dpkg_purge_linux_image(self):
        ctx = _ctx("chroot /mnt dpkg --purge linux-image-5.10.0-amd64")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_chroot_dpkg_purge_shim_signed(self):
        ctx = _ctx("chroot /mnt dpkg --purge shim-signed")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_chroot_apt_remove_grub(self):
        ctx = _ctx("chroot /mnt apt remove grub-pc")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_chroot_apt_purge_linux_image(self):
        ctx = _ctx("chroot /mnt apt purge linux-image-5.10.0")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    # --- WARNING: risky repair commands ---

    def test_chroot_apt_fix_broken(self):
        ctx = _ctx("chroot /mnt apt --fix-broken install")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING
        assert "fix-broken" in violations[0].message

    def test_chroot_dpkg_configure_a(self):
        ctx = _ctx("chroot /mnt dpkg --configure -a")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING
        assert "configure" in violations[0].message

    # --- Config bypass ---

    def test_allowed_ops_bypasses_error(self):
        ctx = _ctx(
            "chroot /mnt dpkg --purge grub-efi-amd64",
            config={"remote-chroot-guard": {"allowed_ops": ["chroot dpkg --purge bootloader package"]}},
        )
        assert self.rule.evaluate(ctx) == []

    def test_allowed_ops_bypasses_warning(self):
        ctx = _ctx(
            "chroot /mnt apt --fix-broken install",
            config={"remote-chroot-guard": {"allowed_ops": ["chroot apt --fix-broken install"]}},
        )
        assert self.rule.evaluate(ctx) == []

    # --- Safe commands ---

    def test_chroot_dpkg_purge_non_bootloader_passes(self):
        ctx = _ctx("chroot /mnt dpkg --purge nginx")
        assert self.rule.evaluate(ctx) == []

    def test_chroot_ls_passes(self):
        ctx = _ctx("chroot /mnt ls /boot")
        assert self.rule.evaluate(ctx) == []

    def test_chroot_cat_passes(self):
        ctx = _ctx("chroot /mnt cat /etc/fstab")
        assert self.rule.evaluate(ctx) == []

    def test_no_chroot_dpkg_purge_passes(self):
        ctx = _ctx("dpkg --purge grub-efi-amd64")
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
            tool_input={"file_path": "s.sh", "content": "chroot /mnt dpkg --purge grub"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []

    # --- Suggestion content ---

    def test_suggestion_mentions_config(self):
        ctx = _ctx("chroot /mnt apt --fix-broken install")
        violations = self.rule.evaluate(ctx)
        assert "allowed_ops" in violations[0].suggestion
