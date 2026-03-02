"""Tests for cloud-paid-resource-creation rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.cloud_paid_resource_creation import CloudPaidResourceCreation


def _ctx(command: str, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
        config=config or {},
    )


class TestCloudPaidResourceCreation:
    rule = CloudPaidResourceCreation()

    # --- GCP patterns ---

    def test_gcloud_compute_addresses_create(self):
        ctx = _ctx("gcloud compute addresses create my-static-ip --region=us-central1")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_gcloud_compute_disks_create(self):
        ctx = _ctx("gcloud compute disks create my-disk --size=100GB --zone=us-central1-a")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_gcloud_compute_instances_create(self):
        ctx = _ctx("gcloud compute instances create my-vm --machine-type=e2-medium")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_gcloud_sql_instances_create(self):
        ctx = _ctx("gcloud sql instances create my-db --database-version=POSTGRES_14")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_gcloud_container_clusters_create(self):
        ctx = _ctx("gcloud container clusters create my-cluster --num-nodes=3")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    # --- AWS patterns ---

    def test_aws_ec2_allocate_address(self):
        ctx = _ctx("aws ec2 allocate-address --domain vpc")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_aws_ec2_run_instances(self):
        ctx = _ctx("aws ec2 run-instances --image-id ami-12345 --instance-type t2.micro")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_aws_rds_create_db_instance(self):
        ctx = _ctx("aws rds create-db-instance --db-instance-identifier mydb --db-instance-class db.t3.micro")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_aws_eks_create_cluster(self):
        ctx = _ctx("aws eks create-cluster --name my-cluster --role-arn arn:aws:iam::...")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    # --- Azure patterns ---

    def test_az_vm_create(self):
        ctx = _ctx("az vm create --name myvm --resource-group mygroup --image Ubuntu2204")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    # --- suppress_warnings config ---

    def test_suppress_warnings_silences_violations(self):
        ctx = _ctx(
            "gcloud compute addresses create my-ip",
            config={"cloud-paid-resource-creation": {"suppress_warnings": True}},
        )
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_suppress_warnings_false_still_fires(self):
        ctx = _ctx(
            "gcloud compute addresses create my-ip",
            config={"cloud-paid-resource-creation": {"suppress_warnings": False}},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- List/describe commands pass through ---

    def test_gcloud_compute_addresses_list_passes(self):
        ctx = _ctx("gcloud compute addresses list")
        assert self.rule.evaluate(ctx) == []

    def test_aws_ec2_describe_instances_passes(self):
        ctx = _ctx("aws ec2 describe-instances")
        assert self.rule.evaluate(ctx) == []

    def test_az_vm_list_passes(self):
        ctx = _ctx("az vm list")
        assert self.rule.evaluate(ctx) == []

    # --- Non-Bash tools ignored ---

    def test_non_bash_tool_ignored(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Edit",
            tool_input={"file_path": "infra.sh", "new_string": "gcloud compute addresses create my-ip"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []

    # --- Message contains cost hint ---

    def test_message_contains_cost_hint(self):
        ctx = _ctx("gcloud compute addresses create my-ip --region=us-central1")
        violations = self.rule.evaluate(ctx)
        assert "$" in violations[0].message or "cost" in violations[0].message.lower()
