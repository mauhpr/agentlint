"""Tests for autopilot pack PreToolUse rules."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.bash_rate_limiter import BashRateLimiter
from agentlint.packs.autopilot.cross_account_guard import CrossAccountGuard
from agentlint.packs.autopilot.destructive_confirmation_gate import DestructiveConfirmationGate
from agentlint.packs.autopilot.dry_run_required import DryRunRequired
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


class TestDryRunRequired:
    rule = DryRunRequired()

    # --- Blocking apply without dry-run ---

    def test_blocks_terraform_apply_without_plan(self):
        ctx = _ctx("Bash", {"command": "terraform apply"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_terraform_apply_auto_approve(self):
        ctx = _ctx("Bash", {"command": "terraform apply -auto-approve"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_ansible_without_check(self):
        ctx = _ctx("Bash", {"command": "ansible-playbook site.yml"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_kubectl_apply_without_dry_run(self):
        ctx = _ctx("Bash", {"command": "kubectl apply -f deployment.yaml"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_helm_upgrade_without_dry_run(self):
        ctx = _ctx("Bash", {"command": "helm upgrade myapp ./chart"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Safe (has dry-run flag) ---

    def test_terraform_plan_passes(self):
        ctx = _ctx("Bash", {"command": "terraform plan"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ansible_check_mode_passes(self):
        ctx = _ctx("Bash", {"command": "ansible-playbook site.yml --check"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_kubectl_apply_dry_run_passes(self):
        ctx = _ctx("Bash", {"command": "kubectl apply -f deployment.yaml --dry-run=client"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_helm_upgrade_dry_run_passes(self):
        ctx = _ctx("Bash", {"command": "helm upgrade myapp ./chart --dry-run"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_kubectl_get_passes(self):
        ctx = _ctx("Bash", {"command": "kubectl get pods"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_bypass_tools_skips_label(self):
        ctx = _ctx(
            "Bash",
            {"command": "terraform apply"},
            config={"dry-run-required": {"bypass_tools": ["terraform apply"]}},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_blocks_pulumi_up_without_preview(self):
        ctx = _ctx("Bash", {"command": "pulumi up"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_pulumi_preview_passes(self):
        ctx = _ctx("Bash", {"command": "pulumi preview"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


class TestBashRateLimiter:
    rule = BashRateLimiter()

    def _ctx_with_state(self, command: str, state: dict | None = None, config: dict | None = None) -> RuleContext:
        return RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": command},
            project_dir="/tmp/project",
            config=config or {},
            session_state=state if state is not None else {},
        )

    def test_allows_first_destructive_op(self):
        ctx = self._ctx_with_state("rm -rf ./dist")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_tracks_destructive_ops_in_state(self):
        state = {}
        ctx = self._ctx_with_state("rm -rf ./dist", state=state)
        self.rule.evaluate(ctx)
        assert "rate_limiter" in state
        assert state["rate_limiter"]["destructive_count"] == 1

    def test_blocks_after_exceeding_limit(self):
        import time
        state = {
            "rate_limiter": {
                "destructive_count": 5,
                "window_start": time.time(),
            }
        }
        ctx = self._ctx_with_state(
            "rm -rf ./logs",
            state=state,
            config={"bash-rate-limiter": {"max_destructive_ops": 5, "window_seconds": 300}},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_resets_after_window_expires(self):
        import time
        state = {
            "rate_limiter": {
                "destructive_count": 5,
                "window_start": time.time() - 400,  # 400s ago → window expired
            }
        }
        ctx = self._ctx_with_state(
            "rm -rf ./logs",
            state=state,
            config={"bash-rate-limiter": {"max_destructive_ops": 5, "window_seconds": 300}},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_non_destructive_command_not_counted(self):
        state = {}
        ctx = self._ctx_with_state("ls -la", state=state)
        self.rule.evaluate(ctx)
        assert state.get("rate_limiter", {}).get("destructive_count", 0) == 0

    def test_drop_database_counted(self):
        state = {}
        ctx = self._ctx_with_state("psql -c 'DROP DATABASE myapp'", state=state)
        self.rule.evaluate(ctx)
        assert state["rate_limiter"]["destructive_count"] == 1


class TestCrossAccountGuard:
    rule = CrossAccountGuard()

    def _ctx_with_state(self, command: str, state: dict | None = None) -> RuleContext:
        return RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": command},
            project_dir="/tmp/project",
            config={},
            session_state=state if state is not None else {},
        )

    def test_first_gcloud_project_registers_no_violation(self):
        state = {}
        ctx = self._ctx_with_state("gcloud --project=my-dev compute instances list", state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0
        assert "cross_account" in state
        assert "my-dev" in state["cross_account"]["seen_gcloud_projects"]

    def test_second_different_gcloud_project_warns(self):
        state = {"cross_account": {"seen_gcloud_projects": ["my-dev"], "seen_aws_profiles": []}}
        ctx = self._ctx_with_state("gcloud --project=my-production compute instances list", state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_same_gcloud_project_no_warning(self):
        state = {"cross_account": {"seen_gcloud_projects": ["my-dev"], "seen_aws_profiles": []}}
        ctx = self._ctx_with_state("gcloud --project=my-dev compute instances list", state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_first_aws_profile_registers_no_violation(self):
        state = {}
        ctx = self._ctx_with_state("aws s3 ls --profile staging", state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_second_different_aws_profile_warns(self):
        state = {"cross_account": {"seen_gcloud_projects": [], "seen_aws_profiles": ["staging"]}}
        ctx = self._ctx_with_state("aws s3 ls --profile production", state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_same_aws_profile_no_warning(self):
        state = {"cross_account": {"seen_gcloud_projects": [], "seen_aws_profiles": ["staging"]}}
        ctx = self._ctx_with_state("aws s3 ls --profile staging", state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_no_project_flag_ignored(self):
        ctx = self._ctx_with_state("gcloud compute instances list")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0
