"""Tests for cloud-resource-deletion rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.cloud_resource_deletion import CloudResourceDeletion


def _ctx(command: str, session_state: dict | None = None, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
        config=config or {},
        session_state=session_state or {},
    )


class TestCloudResourceDeletion:
    rule = CloudResourceDeletion()

    # --- AWS patterns ---

    def test_aws_ec2_terminate_instances(self):
        ctx = _ctx("aws ec2 terminate-instances --instance-ids i-1234567890abcdef0")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_aws_rds_delete_db_instance(self):
        ctx = _ctx("aws rds delete-db-instance --db-instance-identifier mydb")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_aws_s3_rm_recursive(self):
        ctx = _ctx("aws s3 rm s3://my-bucket --recursive")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_aws_dynamodb_delete_table(self):
        ctx = _ctx("aws dynamodb delete-table --table-name MyTable")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_aws_lambda_delete_function(self):
        ctx = _ctx("aws lambda delete-function --function-name my-function")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_aws_iam_delete_user(self):
        ctx = _ctx("aws iam delete-user --user-name myuser")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_aws_iam_delete_role(self):
        ctx = _ctx("aws iam delete-role --role-name myrole")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_aws_cloudformation_delete_stack(self):
        ctx = _ctx("aws cloudformation delete-stack --stack-name mystack")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- GCP patterns ---

    def test_gcloud_compute_instances_delete(self):
        ctx = _ctx("gcloud compute instances delete my-instance --zone=us-central1-a")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_gcloud_sql_instances_delete(self):
        ctx = _ctx("gcloud sql instances delete my-db")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_gcloud_container_clusters_delete(self):
        ctx = _ctx("gcloud container clusters delete my-cluster --zone=us-central1-a")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_gcloud_storage_rm_recursive(self):
        ctx = _ctx("gcloud storage rm gs://my-bucket --recursive")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_gcloud_run_services_delete(self):
        ctx = _ctx("gcloud run services delete my-service --region=us-central1")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Azure patterns ---

    def test_az_vm_delete(self):
        ctx = _ctx("az vm delete --name myvm --resource-group mygroup")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_az_sql_delete(self):
        ctx = _ctx("az sql server delete --name mysqlserver --resource-group mygroup")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_az_group_delete(self):
        ctx = _ctx("az group delete --name mygroup")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_az_storage_account_delete(self):
        ctx = _ctx("az storage account delete --name mystorage --resource-group mygroup")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_az_keyvault_delete(self):
        ctx = _ctx("az keyvault delete --name myvault")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Session-state confirmation ---

    def test_confirmed_op_passes_through(self):
        ctx = _ctx(
            "aws ec2 terminate-instances --instance-ids i-abc",
            session_state={"confirmed_cloud_deletions": ["aws-ec2-terminate"]},
        )
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_confirmed_op_case_insensitive(self):
        ctx = _ctx(
            "aws ec2 terminate-instances --instance-ids i-abc",
            session_state={"confirmed_cloud_deletions": ["AWS-EC2-TERMINATE"]},
        )
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_different_confirmed_op_does_not_bypass(self):
        ctx = _ctx(
            "aws ec2 terminate-instances --instance-ids i-abc",
            session_state={"confirmed_cloud_deletions": ["aws-rds-delete"]},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Config allowed_ops bypass ---

    def test_allowed_ops_config_bypasses(self):
        ctx = _ctx(
            "aws ec2 terminate-instances --instance-ids i-abc",
            config={"cloud-resource-deletion": {"allowed_ops": ["aws-ec2-terminate"]}},
        )
        violations = self.rule.evaluate(ctx)
        assert violations == []

    # --- Safe commands pass through ---

    def test_aws_s3_ls_passes(self):
        ctx = _ctx("aws s3 ls s3://my-bucket")
        assert self.rule.evaluate(ctx) == []

    def test_aws_ec2_describe_instances_passes(self):
        ctx = _ctx("aws ec2 describe-instances")
        assert self.rule.evaluate(ctx) == []

    def test_gcloud_compute_instances_list_passes(self):
        ctx = _ctx("gcloud compute instances list")
        assert self.rule.evaluate(ctx) == []

    def test_aws_s3_rm_without_recursive_passes(self):
        ctx = _ctx("aws s3 rm s3://my-bucket/specific-file.txt")
        assert self.rule.evaluate(ctx) == []

    # --- Non-Bash tools ignored ---

    def test_non_bash_tool_ignored(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "script.sh", "content": "aws ec2 terminate-instances --instance-ids i-abc"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []

    # --- Suggestion contains confirmation key ---

    def test_suggestion_mentions_confirmation_key(self):
        ctx = _ctx("aws ec2 terminate-instances --instance-ids i-abc")
        violations = self.rule.evaluate(ctx)
        assert "aws-ec2-terminate" in violations[0].suggestion
