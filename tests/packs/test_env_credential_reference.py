"""Tests for env-credential-reference rule."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.security.env_credential_reference import EnvCredentialReference


def _bash_ctx(command: str) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
    )


def _write_ctx(content: str) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": "cloudbuild.yaml", "content": content},
        project_dir="/tmp/project",
    )


def _edit_ctx(new_string: str) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Edit",
        tool_input={"file_path": ".github/workflows/deploy.yml", "old_string": "x", "new_string": new_string},
        project_dir="/tmp/project",
    )


class TestEnvCredentialReference:
    rule = EnvCredentialReference()

    # --- Cloud Run --set-env-vars patterns ---

    def test_cloud_run_proxy_file_env_var(self):
        ctx = _bash_ctx(
            'gcloud run deploy myservice --set-env-vars "EZ_PROXIES_LIST_FILE=config/proxies/ezproxies.txt"'
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_cloud_run_secret_file_env_var(self):
        ctx = _bash_ctx(
            'gcloud run deploy myservice --set-env-vars "SECRET_KEY_FILE=config/secrets/key.pem"'
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_cloud_run_token_file_env_var(self):
        ctx = _bash_ctx(
            'gcloud run deploy myservice --set-env-vars "AUTH_TOKEN_FILE=credentials/token.json"'
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_cloud_run_cert_file_env_var(self):
        ctx = _bash_ctx(
            'gcloud run deploy myservice --set-env-vars "TLS_CERT_FILE=config/tls/cert.pem"'
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Credential file in config/secrets paths ---

    def test_secret_file_in_secrets_dir(self):
        ctx = _bash_ctx("SECRET_KEY_FILE=secrets/api_key.txt ./run.sh")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_config_file_in_config_dir(self):
        ctx = _bash_ctx("PROXY_LIST_FILE=config/proxies.txt ./run.sh")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_creds_dir_triggers_warning(self):
        ctx = _bash_ctx("AUTH_FILE=creds/service_account.json ./deploy.sh")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Write tool with credential file references ---

    def test_write_with_credential_env_var(self):
        ctx = _write_ctx("EZ_PROXIES_LIST_FILE=config/proxies/list.txt")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_edit_with_credential_env_var(self):
        ctx = _edit_ctx("SECRET_KEY_FILE=config/secrets/key.pem")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Safe env vars pass through ---

    def test_database_url_not_file_passes(self):
        ctx = _bash_ctx("DATABASE_URL=postgres://user:pass@localhost/mydb ./run.sh")
        assert self.rule.evaluate(ctx) == []

    def test_log_level_env_var_passes(self):
        ctx = _bash_ctx('gcloud run deploy myservice --set-env-vars "LOG_LEVEL=INFO"')
        assert self.rule.evaluate(ctx) == []

    def test_port_env_var_passes(self):
        ctx = _bash_ctx('gcloud run deploy myservice --set-env-vars "PORT=8080"')
        assert self.rule.evaluate(ctx) == []

    def test_api_url_env_var_passes(self):
        ctx = _bash_ctx("API_URL=https://api.example.com ./run.sh")
        assert self.rule.evaluate(ctx) == []

    # --- Suggestion quality ---

    def test_suggestion_mentions_secret_manager(self):
        ctx = _bash_ctx(
            'gcloud run deploy myservice --set-env-vars "SECRET_KEY_FILE=config/key.pem"'
        )
        violations = self.rule.evaluate(ctx)
        assert "Secret Manager" in violations[0].suggestion or "gitignore" in violations[0].suggestion

    # --- Secret Manager bypass (legitimate Cloud Run references) ---

    def test_secret_manager_reference_passes(self):
        ctx = _bash_ctx(
            'gcloud run deploy svc --set-env-vars "MY_KEY_FILE=Secret:my-secret-name"'
        )
        assert self.rule.evaluate(ctx) == []

    def test_secretmanager_uri_reference_passes(self):
        ctx = _bash_ctx(
            'gcloud run deploy svc --set-env-vars "AUTH_KEY_FILE=secretmanager:projects/p/secrets/s"'
        )
        assert self.rule.evaluate(ctx) == []

    def test_cloud_run_quoted_var_triggers(self):
        ctx = _bash_ctx(
            'gcloud run deploy svc --set-env-vars "SECRET_KEY_FILE=config/key.pem"'
        )
        assert len(self.rule.evaluate(ctx)) == 1

    # --- Non-monitored tools ignored ---

    def test_read_tool_ignored(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Read",
            tool_input={"file_path": "SECRET_KEY_FILE=config/key.pem"},
            project_dir="/tmp",
        )
        assert self.rule.evaluate(ctx) == []
