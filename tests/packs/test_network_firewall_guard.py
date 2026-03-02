"""Tests for network-firewall-guard rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.network_firewall_guard import NetworkFirewallGuard


def _ctx(command: str) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
    )


class TestNetworkFirewallGuard:
    rule = NetworkFirewallGuard()

    # --- iptables ---

    def test_iptables_flush(self):
        ctx = _ctx("iptables -F")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_iptables_chain_deletion(self):
        ctx = _ctx("iptables -X")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_iptables_allow_all_ips(self):
        ctx = _ctx("iptables -A INPUT -s 0.0.0.0/0 -j ACCEPT")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_iptables_list_passes(self):
        ctx = _ctx("iptables -L")
        assert self.rule.evaluate(ctx) == []

    def test_iptables_specific_cidr_passes(self):
        ctx = _ctx("iptables -A INPUT -s 10.0.0.0/8 -j ACCEPT")
        assert self.rule.evaluate(ctx) == []

    # --- ufw ---

    def test_ufw_disable(self):
        ctx = _ctx("ufw disable")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_ufw_allow_from_any(self):
        ctx = _ctx("ufw allow from any to any port 22")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ufw_allow_from_cidr_0000(self):
        ctx = _ctx("ufw allow from 0.0.0.0/0 to any port 22")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ufw_status_passes(self):
        ctx = _ctx("ufw status")
        assert self.rule.evaluate(ctx) == []

    def test_ufw_allow_specific_ip_passes(self):
        ctx = _ctx("ufw allow from 192.168.1.0/24 to any port 22")
        assert self.rule.evaluate(ctx) == []

    # --- firewalld ---

    def test_firewalld_permanent_add_port(self):
        ctx = _ctx("firewall-cmd --zone=public --add-port=3306/tcp --permanent")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_firewalld_public_zone_add_service(self):
        ctx = _ctx("firewall-cmd --zone=public --add-service=mysql")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_firewalld_list_all_passes(self):
        ctx = _ctx("firewall-cmd --list-all")
        assert self.rule.evaluate(ctx) == []

    # --- Route mutations ---

    def test_route_add_default(self):
        ctx = _ctx("route add default gw 10.0.0.1")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ip_route_add_default(self):
        ctx = _ctx("ip route add default via 192.168.1.1")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ip_route_del_default(self):
        ctx = _ctx("ip route del default")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- DNS overwrite ---

    def test_resolv_conf_overwrite(self):
        ctx = _ctx("echo 'nameserver 8.8.8.8' > /etc/resolv.conf")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- allowed_ops config bypass ---

    def test_allowed_ops_bypasses_iptables_flush(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "iptables -F"},
            project_dir="/tmp",
            config={"network-firewall-guard": {"allowed_ops": ["iptables flush (removes all rules)"]}},
        )
        assert self.rule.evaluate(ctx) == []

    def test_allowed_ops_does_not_bypass_other_operations(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "ufw disable"},
            project_dir="/tmp",
            config={"network-firewall-guard": {"allowed_ops": ["iptables flush (removes all rules)"]}},
        )
        assert len(self.rule.evaluate(ctx)) == 1

    # --- Non-Bash tools ignored ---

    def test_non_bash_tool_ignored(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "script.sh", "content": "iptables -F"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []
