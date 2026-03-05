"""Tests for package-manager-in-chroot rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.package_manager_in_chroot import PackageManagerInChroot


def _ctx(command: str, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
        config=config or {},
    )


class TestPackageManagerInChroot:
    rule = PackageManagerInChroot()

    # --- Debian/Ubuntu ---

    def test_chroot_apt_install(self):
        ctx = _ctx("chroot /mnt apt install nginx")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING
        assert "apt" in violations[0].message

    def test_chroot_apt_update(self):
        ctx = _ctx("chroot /mnt apt update")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_chroot_apt_upgrade(self):
        ctx = _ctx("chroot /mnt apt upgrade")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_chroot_apt_dist_upgrade(self):
        ctx = _ctx("chroot /mnt apt dist-upgrade")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_chroot_apt_autoremove(self):
        ctx = _ctx("chroot /mnt apt autoremove")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_chroot_dpkg_i(self):
        ctx = _ctx("chroot /mnt dpkg -i /tmp/package.deb")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "dpkg" in violations[0].message

    # --- RHEL/Fedora ---

    def test_chroot_yum_install(self):
        ctx = _ctx("chroot /mnt yum install httpd")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_chroot_yum_remove(self):
        ctx = _ctx("chroot /mnt yum remove httpd")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_chroot_yum_update(self):
        ctx = _ctx("chroot /mnt yum update")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_chroot_dnf_install(self):
        ctx = _ctx("chroot /mnt dnf install nginx")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_chroot_dnf_remove(self):
        ctx = _ctx("chroot /mnt dnf remove nginx")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_chroot_dnf_update(self):
        ctx = _ctx("chroot /mnt dnf update")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Arch ---

    def test_chroot_pacman_S(self):
        ctx = _ctx("chroot /mnt pacman -S nginx")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_chroot_pacman_R(self):
        ctx = _ctx("chroot /mnt pacman -R nginx")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_chroot_pacman_U(self):
        ctx = _ctx("chroot /mnt pacman -U /tmp/pkg.tar.zst")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Config bypass ---

    def test_allowed_ops_bypasses(self):
        ctx = _ctx(
            "chroot /mnt apt install nginx",
            config={"package-manager-in-chroot": {"allowed_ops": ["chroot apt install/update/upgrade"]}},
        )
        assert self.rule.evaluate(ctx) == []

    def test_different_allowed_op_no_bypass(self):
        ctx = _ctx(
            "chroot /mnt apt install nginx",
            config={"package-manager-in-chroot": {"allowed_ops": ["chroot dpkg -i"]}},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Safe commands ---

    def test_chroot_ls_passes(self):
        ctx = _ctx("chroot /mnt ls /etc/apt")
        assert self.rule.evaluate(ctx) == []

    def test_no_chroot_apt_install_passes(self):
        ctx = _ctx("apt install nginx")
        assert self.rule.evaluate(ctx) == []

    def test_chroot_cat_passes(self):
        ctx = _ctx("chroot /mnt cat /etc/os-release")
        assert self.rule.evaluate(ctx) == []

    # --- Safe read-only apt operations ---

    def test_chroot_apt_search_passes(self):
        ctx = _ctx("chroot /mnt apt search nginx")
        assert self.rule.evaluate(ctx) == []

    def test_chroot_apt_show_passes(self):
        ctx = _ctx("chroot /mnt apt show nginx")
        assert self.rule.evaluate(ctx) == []

    def test_chroot_apt_list_passes(self):
        ctx = _ctx("chroot /mnt apt list --installed")
        assert self.rule.evaluate(ctx) == []

    # --- Config bypass for other package managers ---

    def test_allowed_ops_bypasses_yum(self):
        ctx = _ctx(
            "chroot /mnt yum install httpd",
            config={"package-manager-in-chroot": {"allowed_ops": ["chroot yum install/remove/update"]}},
        )
        assert self.rule.evaluate(ctx) == []

    def test_allowed_ops_bypasses_dnf(self):
        ctx = _ctx(
            "chroot /mnt dnf install nginx",
            config={"package-manager-in-chroot": {"allowed_ops": ["chroot dnf install/remove/update"]}},
        )
        assert self.rule.evaluate(ctx) == []

    def test_allowed_ops_bypasses_pacman(self):
        ctx = _ctx(
            "chroot /mnt pacman -S nginx",
            config={"package-manager-in-chroot": {"allowed_ops": ["chroot pacman -S/-R/-U"]}},
        )
        assert self.rule.evaluate(ctx) == []

    # --- Edge cases ---

    def test_empty_command_passes(self):
        ctx = _ctx("")
        assert self.rule.evaluate(ctx) == []

    def test_chroot_apt_get_install(self):
        ctx = _ctx("chroot /mnt apt-get install nginx")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "apt" in violations[0].message

    # --- Non-Bash tool ignored ---

    def test_non_bash_tool_ignored(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "s.sh", "content": "chroot /mnt apt install nginx"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []

    # --- Suggestion content ---

    def test_suggestion_mentions_config(self):
        ctx = _ctx("chroot /mnt apt install nginx")
        violations = self.rule.evaluate(ctx)
        assert "allowed_ops" in violations[0].suggestion
