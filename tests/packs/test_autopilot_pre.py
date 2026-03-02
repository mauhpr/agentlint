"""Tests for autopilot pack PreToolUse rules."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.destructive_confirmation_gate import DestructiveConfirmationGate
from agentlint.packs.autopilot.production_guard import ProductionGuard


def _ctx(tool_name: str, tool_input: dict, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
        config=config or {},
    )


class TestProductionGuard:
    rule = ProductionGuard()

    # --- Detection ---

    def test_blocks_psql_prod_connection_string(self):
        ctx = _ctx("Bash", {"command": "psql postgresql://user:pass@prod-db.example.com/myapp"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_psql_production_database_name(self):
        ctx = _ctx("Bash", {"command": "psql -h localhost -d production -U admin"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_gcloud_prod_project(self):
        ctx = _ctx("Bash", {"command": "gcloud --project=my-production-project deploy"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_gcloud_project_flag_prod(self):
        ctx = _ctx("Bash", {"command": "gcloud compute instances list --project prod-env-123"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_aws_prod_profile(self):
        ctx = _ctx("Bash", {"command": "aws s3 ls --profile production"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_aws_prod_account_env(self):
        ctx = _ctx("Bash", {"command": "AWS_PROFILE=prod aws ec2 describe-instances"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_mysql_prod_host(self):
        ctx = _ctx("Bash", {"command": "mysql -h prod-mysql.internal -u root -p mydb"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_connection_string_with_live(self):
        ctx = _ctx("Bash", {"command": "psql postgresql://user:pass@live-db.example.com/app"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_psql_prod_host_flag(self):
        ctx = _ctx("Bash", {"command": "psql -h prod-db.internal -U admin myapp"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Allowlist ---

    def test_allowed_project_passes(self):
        ctx = _ctx(
            "Bash",
            {"command": "gcloud --project=my-production-project deploy"},
            config={"production-guard": {"allowed_projects": ["my-production-project"]}},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allowed_host_passes(self):
        ctx = _ctx(
            "Bash",
            {"command": "psql -h prod-db.example.com -d myapp"},
            config={"production-guard": {"allowed_hosts": ["prod-db.example.com"]}},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    # --- Non-production pass through ---

    def test_dev_database_passes(self):
        ctx = _ctx("Bash", {"command": "psql -h localhost -d myapp_dev -U admin"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_staging_database_passes(self):
        ctx = _ctx("Bash", {"command": "psql -h staging-db.internal -d myapp_staging -U user"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_gcloud_dev_project_passes(self):
        ctx = _ctx("Bash", {"command": "gcloud --project=my-dev-project compute instances list"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_non_bash_tool_ignored(self):
        ctx = _ctx("Write", {"file_path": "prod.py", "content": "x=1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


class TestDestructiveConfirmationGate:
    rule = DestructiveConfirmationGate()

    def _ctx_with_state(self, command: str, state: dict | None = None) -> RuleContext:
        return RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": command},
            project_dir="/tmp/project",
            config={},
            session_state=state or {},
        )

    # --- Blocking without confirmation ---

    def test_blocks_drop_database_without_confirmation(self):
        ctx = self._ctx_with_state("psql -c 'DROP DATABASE myapp'")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_terraform_destroy_without_confirmation(self):
        ctx = self._ctx_with_state("terraform destroy -auto-approve")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_kubectl_delete_namespace_without_confirmation(self):
        ctx = self._ctx_with_state("kubectl delete namespace production")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_drop_table_without_confirmation(self):
        ctx = self._ctx_with_state("psql -c 'DROP TABLE users CASCADE'")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_gcloud_delete_project(self):
        ctx = self._ctx_with_state("gcloud projects delete my-project")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Passes with confirmation in session state ---

    def test_passes_with_confirmation_flag(self):
        state = {"confirmed_destructive_ops": ["DROP DATABASE"]}
        ctx = self._ctx_with_state("psql -c 'DROP DATABASE myapp'", state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_passes_terraform_destroy_with_confirmation(self):
        state = {"confirmed_destructive_ops": ["terraform destroy"]}
        ctx = self._ctx_with_state("terraform destroy -auto-approve", state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    # --- Safe commands pass through ---

    def test_terraform_plan_passes(self):
        ctx = self._ctx_with_state("terraform plan")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_kubectl_get_passes(self):
        ctx = self._ctx_with_state("kubectl get pods")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_psql_select_passes(self):
        ctx = self._ctx_with_state("psql -c 'SELECT * FROM users LIMIT 10'")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0
