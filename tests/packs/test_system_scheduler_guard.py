"""Tests for system-scheduler-guard rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.system_scheduler_guard import SystemSchedulerGuard


def _bash_ctx(command: str) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
    )


def _file_ctx(tool_name: str, file_path: str) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input={"file_path": file_path, "content": "# scheduler config"},
        project_dir="/tmp/project",
    )


class TestSystemSchedulerGuard:
    rule = SystemSchedulerGuard()

    # --- Cron bash patterns ---

    def test_crontab_e_triggers_warning(self):
        ctx = _bash_ctx("crontab -e")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_crontab_pipe_injection_triggers_warning(self):
        ctx = _bash_ctx('echo "* * * * * /usr/bin/curl http://example.com" | crontab')
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_crontab_without_args_triggers_warning(self):
        ctx = _bash_ctx("crontab /tmp/mycron")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- crontab -l and -u user are read-only, should pass ---

    def test_crontab_l_passes(self):
        ctx = _bash_ctx("crontab -l")
        assert self.rule.evaluate(ctx) == []

    def test_crontab_u_user_read_only_passes(self):
        ctx = _bash_ctx("crontab -u myuser")
        assert self.rule.evaluate(ctx) == []

    def test_crontab_r_remove_triggers_warning(self):
        ctx = _bash_ctx("crontab -r")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    # --- systemd patterns ---

    def test_systemctl_enable_triggers_warning(self):
        ctx = _bash_ctx("systemctl enable myservice")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_systemctl_disable_triggers_warning(self):
        ctx = _bash_ctx("systemctl disable myservice")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_systemctl_mask_triggers_warning(self):
        ctx = _bash_ctx("systemctl mask myservice")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_systemctl_daemon_reload_triggers_warning(self):
        ctx = _bash_ctx("systemctl daemon-reload")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- systemctl read-only commands pass ---

    def test_systemctl_status_passes(self):
        ctx = _bash_ctx("systemctl status nginx")
        assert self.rule.evaluate(ctx) == []

    def test_systemctl_restart_passes(self):
        ctx = _bash_ctx("systemctl restart nginx")
        assert self.rule.evaluate(ctx) == []

    def test_systemctl_list_units_passes(self):
        ctx = _bash_ctx("systemctl list-units")
        assert self.rule.evaluate(ctx) == []

    # --- launchctl patterns ---

    def test_launchctl_load_triggers_warning(self):
        ctx = _bash_ctx("launchctl load /Library/LaunchDaemons/com.example.plist")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_launchctl_bootstrap_triggers_warning(self):
        ctx = _bash_ctx("launchctl bootstrap system /Library/LaunchDaemons/com.example.plist")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- at scheduler ---

    def test_at_now_triggers_warning(self):
        ctx = _bash_ctx("at now + 5 minutes")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_at_digit_triggers_warning(self):
        ctx = _bash_ctx("echo 'do something' | at 14:30")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- File write to scheduler paths ---

    def test_write_to_etc_cron_d_triggers_warning(self):
        ctx = _file_ctx("Write", "/etc/cron.d/myjob")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_write_to_etc_crontab_triggers_warning(self):
        ctx = _file_ctx("Write", "/etc/crontab")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_write_to_etc_systemd_system_triggers_warning(self):
        ctx = _file_ctx("Write", "/etc/systemd/system/myservice.service")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_edit_to_lib_launch_daemons_triggers_warning(self):
        ctx = _file_ctx("Edit", "/Library/LaunchDaemons/com.example.plist")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_write_to_home_launch_agents_triggers_warning(self):
        ctx = _file_ctx("Write", "/Users/user/Library/LaunchAgents/com.example.plist")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Normal file writes pass ---

    def test_write_to_normal_path_passes(self):
        ctx = _file_ctx("Write", "/home/user/script.sh")
        assert self.rule.evaluate(ctx) == []

    def test_write_to_etc_nginx_passes(self):
        ctx = _file_ctx("Write", "/etc/nginx/nginx.conf")
        assert self.rule.evaluate(ctx) == []
