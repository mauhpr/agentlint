"""Tests for cloud-infra-mutation rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.cloud_infra_mutation import CloudInfraMutation


def _ctx(command: str, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
        config=config or {},
    )


class TestCloudInfraMutation:
    rule = CloudInfraMutation()

    # --- GCP patterns ---

    def test_gcloud_nat_update(self):
        ctx = _ctx("gcloud compute routers nats update wag-nat --nat-external-ip-pool=ip1,ip2")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_gcloud_nat_create(self):
        ctx = _ctx("gcloud compute routers nats create my-nat --router=my-router")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_gcloud_firewall_rule_create(self):
        ctx = _ctx("gcloud compute firewall-rules create allow-http --allow=tcp:80")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_gcloud_firewall_rule_update(self):
        ctx = _ctx("gcloud compute firewall-rules update my-rule --priority=900")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_gcloud_backend_service_update(self):
        ctx = _ctx("gcloud compute backend-services update my-backend --global")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_gcloud_forwarding_rule_create(self):
        ctx = _ctx("gcloud compute forwarding-rules create my-rule --load-balancing-scheme=EXTERNAL")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_gcloud_vpc_network_create(self):
        ctx = _ctx("gcloud compute networks create my-vpc --subnet-mode=custom")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_gcloud_iam_policy_binding(self):
        ctx = _ctx("gcloud projects add-iam-policy-binding my-project --member=user:test@example.com --role=roles/editor")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- AWS patterns ---

    def test_aws_security_group_authorize_ingress(self):
        ctx = _ctx("aws ec2 authorize-security-group-ingress --group-id sg-123 --protocol tcp --port 22 --cidr 0.0.0.0/0")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_aws_security_group_revoke_egress(self):
        ctx = _ctx("aws ec2 revoke-security-group-egress --group-id sg-123 --protocol tcp --port 443")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_aws_iam_attach_role_policy(self):
        ctx = _ctx("aws iam attach-role-policy --role-name MyRole --policy-arn arn:aws:iam::aws:policy/AdministratorAccess")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_aws_iam_put_user_policy(self):
        ctx = _ctx("aws iam put-user-policy --user-name myuser --policy-name mypolicy --policy-document file://policy.json")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_aws_ec2_create_route(self):
        ctx = _ctx("aws ec2 create-route --route-table-id rtb-123 --destination-cidr-block 0.0.0.0/0 --gateway-id igw-abc")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_aws_elbv2_modify_listener(self):
        ctx = _ctx("aws elbv2 modify-listener --listener-arn arn:aws:elasticloadbalancing:... --protocol HTTPS")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Azure patterns ---

    def test_az_nsg_rule_create(self):
        ctx = _ctx("az network nsg rule create --nsg-name myNSG --name AllowSSH --priority 100 --access Allow")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_az_vnet_create(self):
        ctx = _ctx("az network vnet create --name myVNet --resource-group myRG --address-prefix 10.0.0.0/16")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_az_role_assignment_create(self):
        ctx = _ctx("az role assignment create --assignee user@example.com --role Contributor --scope /subscriptions/...")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Read-only commands pass through ---

    def test_gcloud_firewall_rules_list_passes(self):
        ctx = _ctx("gcloud compute firewall-rules list")
        assert self.rule.evaluate(ctx) == []

    def test_aws_ec2_describe_security_groups_passes(self):
        ctx = _ctx("aws ec2 describe-security-groups")
        assert self.rule.evaluate(ctx) == []

    def test_gcloud_compute_routers_describe_passes(self):
        ctx = _ctx("gcloud compute routers describe my-router")
        assert self.rule.evaluate(ctx) == []

    def test_aws_iam_list_policies_passes(self):
        ctx = _ctx("aws iam list-policies")
        assert self.rule.evaluate(ctx) == []

    # --- Config allowed_operations bypass ---

    def test_allowed_ops_config_bypasses(self):
        ctx = _ctx(
            "gcloud compute routers nats update wag-nat --nat-external-ip-pool=ip1",
            config={"cloud-infra-mutation": {"allowed_ops": ["GCP Cloud NAT update"]}},
        )
        violations = self.rule.evaluate(ctx)
        assert violations == []

    # --- Non-Bash tools ignored ---

    def test_non_bash_tool_ignored(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "script.sh", "content": "gcloud compute routers nats update"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []
