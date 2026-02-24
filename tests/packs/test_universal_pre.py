"""Tests for universal pack PreToolUse rules."""
from __future__ import annotations

import pytest

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.universal.dependency_hygiene import DependencyHygiene
from agentlint.packs.universal.no_destructive_commands import NoDestructiveCommands
from agentlint.packs.universal.no_env_commit import NoEnvCommit
from agentlint.packs.universal.no_force_push import NoForcePush
from agentlint.packs.universal.no_push_to_main import NoPushToMain
from agentlint.packs.universal.no_secrets import NoSecrets
from agentlint.packs.universal.no_skip_hooks import NoSkipHooks
from agentlint.packs.universal.no_test_weakening import NoTestWeakening


def _ctx(tool_name: str, tool_input: dict, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
        config=config or {},
    )


# ---------------------------------------------------------------------------
# NoSecrets
# ---------------------------------------------------------------------------


class TestNoSecrets:
    rule = NoSecrets()

    def test_blocks_api_key_in_write(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'api_key = "sk_live_abc123xyz456789012"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1
        assert any("secret" in v.message.lower() or "api_key" in v.message.lower() for v in violations)

    def test_blocks_password_assignment(self):
        ctx = _ctx("Write", {
            "file_path": "settings.py",
            "content": 'password = "SuperS3cretP@ssw0rd!!"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_blocks_bearer_token(self):
        ctx = _ctx("Edit", {
            "file_path": "app.py",
            "content": 'headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"}',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_blocks_aws_key(self):
        ctx = _ctx("Write", {
            "file_path": "deploy.py",
            "content": "aws_key = 'AKIAIOSFODNN7EXAMPLE'",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_blocks_github_token(self):
        ctx = _ctx("Write", {
            "file_path": "ci.py",
            "content": "token = 'ghp_ABCDEFghijklmnopqrstuvwxyz1234567890'",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_allows_env_var_reference(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'api_key = os.environ["MY_API_KEY"]',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_placeholder_value(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'api_key = "placeholder"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_test_value(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'secret_key = "changeme"',
        })
        violations = self.rule.evaluate(ctx)
        # changeme is 8 chars — below the 10-char threshold, so no match anyway
        assert len(violations) == 0

    def test_detects_secret_in_bash_command(self):
        ctx = _ctx("Bash", {
            "command": 'echo "api_key = sk_live_supersecret12345"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_detects_bearer_in_bash_curl(self):
        ctx = _ctx("Bash", {
            "command": 'curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_ignores_non_write_non_bash_tool(self):
        ctx = _ctx("Read", {
            "file_path": "config.py",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_blocks_sensitive_filename(self):
        ctx = _ctx("Write", {
            "file_path": "/app/credentials.json",
            "content": "{}",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1


# ---------------------------------------------------------------------------
# NoEnvCommit
# ---------------------------------------------------------------------------


class TestNoEnvCommit:
    rule = NoEnvCommit()

    def test_blocks_env_file(self):
        ctx = _ctx("Write", {"file_path": ".env", "content": "SECRET=abc"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_env_local(self):
        ctx = _ctx("Write", {"file_path": ".env.local", "content": "X=1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_env_production(self):
        ctx = _ctx("Write", {"file_path": ".env.production", "content": "X=1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_env_example(self):
        ctx = _ctx("Write", {"file_path": ".env.example", "content": "X=1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_env_template(self):
        ctx = _ctx("Write", {"file_path": ".env.template", "content": "X=1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_regular_file(self):
        ctx = _ctx("Write", {"file_path": "config.py", "content": "X=1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_blocks_nested_env_file(self):
        """Nested path like config/.env.production should be blocked."""
        ctx = _ctx("Write", {"file_path": "config/.env.production", "content": "SECRET=x"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# NoForcePush
# ---------------------------------------------------------------------------


class TestNoForcePush:
    rule = NoForcePush()

    def test_blocks_force_push_to_main(self):
        ctx = _ctx("Bash", {"command": "git push --force origin main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_f_flag_to_master(self):
        ctx = _ctx("Bash", {"command": "git push -f origin master"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_regular_push(self):
        ctx = _ctx("Bash", {"command": "git push origin main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_warns_force_push_to_feature_branch(self):
        ctx = _ctx("Bash", {"command": "git push --force origin feature/my-branch"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_blocks_force_with_lease_to_main(self):
        ctx = _ctx("Bash", {"command": "git push --force-with-lease origin main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_warns_force_push_no_branch(self):
        ctx = _ctx("Bash", {"command": "git push -f"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_blocks_force_push_case_insensitive_branch(self):
        """Branch names Main, MAIN should also be blocked."""
        ctx = _ctx("Bash", {"command": "git push --force origin Main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_ignores_non_bash_tool(self):
        ctx = _ctx("Write", {"file_path": "x.sh", "content": "git push --force origin main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# NoDestructiveCommands
# ---------------------------------------------------------------------------


class TestNoDestructiveCommands:
    rule = NoDestructiveCommands()

    def test_warns_rm_rf(self):
        ctx = _ctx("Bash", {"command": "rm -rf /important/data"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_warns_drop_table(self):
        ctx = _ctx("Bash", {"command": "psql -c 'DROP TABLE users;'"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_warns_git_reset_hard(self):
        ctx = _ctx("Bash", {"command": "git reset --hard HEAD~3"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_warns_git_clean_fd(self):
        ctx = _ctx("Bash", {"command": "git clean -fd"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_safe_commands(self):
        ctx = _ctx("Bash", {"command": "ls -la && echo hello"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_rm_rf_node_modules(self):
        ctx = _ctx("Bash", {"command": "rm -rf node_modules"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_rm_rf_pycache(self):
        ctx = _ctx("Bash", {"command": "rm -rf __pycache__"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_rm_rf_dist(self):
        ctx = _ctx("Bash", {"command": "rm -rf dist"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_rm_rf_quoted_node_modules(self):
        ctx = _ctx("Bash", {"command": "rm -rf 'node_modules'"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_warns_rm_fr(self):
        ctx = _ctx("Bash", {"command": "rm -fr /important/data"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING


# ---------------------------------------------------------------------------
# DependencyHygiene
# ---------------------------------------------------------------------------


class TestDependencyHygiene:
    rule = DependencyHygiene()

    def test_warns_pip_install(self):
        ctx = _ctx("Bash", {"command": "pip install requests"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "poetry/uv" in violations[0].suggestion

    def test_warns_npm_install_package(self):
        ctx = _ctx("Bash", {"command": "npm install express"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "npm ci" in violations[0].suggestion

    def test_allows_pip_install_editable(self):
        ctx = _ctx("Bash", {"command": "pip install -e ."})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_npm_install_bare(self):
        ctx = _ctx("Bash", {"command": "npm install"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_npm_ci(self):
        ctx = _ctx("Bash", {"command": "npm ci"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_poetry_add(self):
        ctx = _ctx("Bash", {"command": "poetry add requests"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_uv_add(self):
        ctx = _ctx("Bash", {"command": "uv add requests"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_pip_install_requirements(self):
        ctx = _ctx("Bash", {"command": "pip install -r requirements.txt"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_pip_install_r_dev(self):
        ctx = _ctx("Bash", {"command": "pip install -r requirements-dev.txt"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_warns_pip3_install(self):
        """pip3 install should also be caught."""
        ctx = _ctx("Bash", {"command": "pip3 install requests"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# NoEnvCommit — Bash extension
# ---------------------------------------------------------------------------


class TestNoEnvCommitBash:
    rule = NoEnvCommit()

    def test_blocks_echo_to_env(self):
        ctx = _ctx("Bash", {"command": 'echo "SECRET=value" > .env'})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_cat_heredoc_to_env(self):
        ctx = _ctx("Bash", {"command": "cat > .env << EOF\nSECRET=real\nEOF"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_tee_to_env(self):
        ctx = _ctx("Bash", {"command": 'echo "X=1" | tee .env'})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_cp_to_env(self):
        ctx = _ctx("Bash", {"command": "cp .env.example .env"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_sed_on_env(self):
        ctx = _ctx("Bash", {"command": "sed -i 's/old/new/' .env"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_env_local_via_bash(self):
        ctx = _ctx("Bash", {"command": 'echo "X=1" > .env.local'})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_env_example_via_bash(self):
        ctx = _ctx("Bash", {"command": "cp template .env.example"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_non_env_file(self):
        ctx = _ctx("Bash", {"command": 'echo "hello" > config.txt'})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_write_with_no_file_path(self):
        ctx = _ctx("Write", {"content": "SECRET=abc"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_empty_bash_command(self):
        ctx = _ctx("Bash", {"command": ""})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_deduplicates_same_env_target(self):
        """Bash command referencing .env twice should produce one violation."""
        ctx = _ctx("Bash", {"command": 'echo "A=1" > .env && echo "B=2" >> .env'})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# NoDestructiveCommands — new patterns
# ---------------------------------------------------------------------------


class TestNoDestructiveCommandsExpanded:
    rule = NoDestructiveCommands()

    def test_warns_chmod_777(self):
        ctx = _ctx("Bash", {"command": "chmod 777 /var/www"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_warns_chmod_recursive_777(self):
        ctx = _ctx("Bash", {"command": "chmod -R 777 /opt"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_error_mkfs(self):
        ctx = _ctx("Bash", {"command": "mkfs.ext4 /dev/sda1"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1
        assert any(v.severity == Severity.ERROR for v in violations)

    def test_error_dd_zero(self):
        ctx = _ctx("Bash", {"command": "dd if=/dev/zero of=/dev/sda bs=1M"})
        violations = self.rule.evaluate(ctx)
        assert any(v.severity == Severity.ERROR for v in violations)

    def test_error_fork_bomb(self):
        ctx = _ctx("Bash", {"command": ":(){ :|:& };:"})
        violations = self.rule.evaluate(ctx)
        assert any(v.severity == Severity.ERROR for v in violations)

    def test_error_rm_rf_root(self):
        ctx = _ctx("Bash", {"command": "rm -rf / "})
        violations = self.rule.evaluate(ctx)
        assert any(v.severity == Severity.ERROR for v in violations)

    def test_error_rm_rf_home(self):
        ctx = _ctx("Bash", {"command": "rm -rf ~"})
        violations = self.rule.evaluate(ctx)
        assert any(v.severity == Severity.ERROR for v in violations)

    def test_warns_docker_prune(self):
        ctx = _ctx("Bash", {"command": "docker system prune -a --volumes"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_warns_kubectl_delete_namespace(self):
        ctx = _ctx("Bash", {"command": "kubectl delete namespace production"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_error_git_branch_delete_main(self):
        ctx = _ctx("Bash", {"command": "git branch -D main"})
        violations = self.rule.evaluate(ctx)
        assert any(v.severity == Severity.ERROR for v in violations)

    def test_error_git_branch_delete_master(self):
        ctx = _ctx("Bash", {"command": "git branch -D master"})
        violations = self.rule.evaluate(ctx)
        assert any(v.severity == Severity.ERROR for v in violations)

    def test_allows_git_branch_delete_feature(self):
        """Deleting feature branches should not trigger."""
        ctx = _ctx("Bash", {"command": "git branch -D feature/my-branch"})
        violations = self.rule.evaluate(ctx)
        # Should not have ERROR for feature branches
        assert not any(v.severity == Severity.ERROR for v in violations)

    def test_allows_chmod_644(self):
        ctx = _ctx("Bash", {"command": "chmod 644 file.txt"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_safe_dd(self):
        """dd without /dev/zero should be allowed."""
        ctx = _ctx("Bash", {"command": "dd if=image.iso of=/dev/sdx bs=4M"})
        violations = self.rule.evaluate(ctx)
        assert not any("dd if=/dev/zero" in v.message for v in violations)

    # --- False positive regressions ---

    def test_allows_stderr_redirect_with_pipe(self):
        """2>/dev/null | command is stderr suppression, not a fork bomb."""
        ctx = _ctx("Bash", {"command": "printenv | grep -i 'database' 2>/dev/null | head -5"})
        violations = self.rule.evaluate(ctx)
        assert not any("Fork bomb" in v.message for v in violations)

    def test_allows_gcloud_with_dev_null(self):
        """gcloud command with 2>/dev/null should not trigger fork bomb."""
        ctx = _ctx("Bash", {"command": "gcloud sql instances list 2>/dev/null | head -5"})
        violations = self.rule.evaluate(ctx)
        assert not any("Fork bomb" in v.message for v in violations)

    def test_allows_any_command_with_stderr_suppression(self):
        """Any command piping with 2>/dev/null is normal shell usage."""
        ctx = _ctx("Bash", {"command": "cat /etc/hosts 2>/dev/null | grep localhost"})
        violations = self.rule.evaluate(ctx)
        assert not any("Fork bomb" in v.message for v in violations)

    def test_still_detects_real_fork_bomb(self):
        """Actual fork bomb syntax should still be caught."""
        ctx = _ctx("Bash", {"command": ":(){ :|:& };:"})
        violations = self.rule.evaluate(ctx)
        assert any(v.severity == Severity.ERROR for v in violations)
        assert any("Fork bomb" in v.message for v in violations)


# ---------------------------------------------------------------------------
# NoSecrets — new patterns
# ---------------------------------------------------------------------------


class TestNoSecretsExpanded:
    rule = NoSecrets()

    def test_detects_slack_bot_token(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'SLACK_TOKEN = "xoxb-1234567890-abcdef"',
        })
        violations = self.rule.evaluate(ctx)
        assert any("xoxb-" in v.message for v in violations)

    def test_detects_slack_user_token(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'token = "xoxp-1234567890-abcdef"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_detects_private_key(self):
        ctx = _ctx("Write", {
            "file_path": "key.pem",
            "content": "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA...",
        })
        violations = self.rule.evaluate(ctx)
        assert any("Private key" in v.message for v in violations)

    def test_detects_ec_private_key(self):
        ctx = _ctx("Write", {
            "file_path": "key.pem",
            "content": "-----BEGIN EC PRIVATE KEY-----\nMHQCAQEEI...",
        })
        violations = self.rule.evaluate(ctx)
        assert any("Private key" in v.message for v in violations)

    def test_detects_gcp_service_account(self):
        ctx = _ctx("Write", {
            "file_path": "service-account.json",
            "content": '{"type": "service_account", "project_id": "my-project"}',
        })
        violations = self.rule.evaluate(ctx)
        assert any("service account" in v.message.lower() for v in violations)

    def test_detects_postgres_connection_string(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'DATABASE_URL = "postgres://admin:r3alp@ss!@db.example.com/mydb"',
        })
        violations = self.rule.evaluate(ctx)
        assert any("Database connection" in v.message for v in violations)

    def test_allows_postgres_localhost_placeholder(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'DATABASE_URL = "postgres://user:password@localhost/testdb"',
        })
        violations = self.rule.evaluate(ctx)
        assert not any("Database connection" in v.message for v in violations)

    def test_detects_jwt_token(self):
        ctx = _ctx("Write", {
            "file_path": "auth.py",
            "content": 'token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"',
        })
        violations = self.rule.evaluate(ctx)
        assert any("JWT" in v.message for v in violations)

    def test_detects_curl_auth(self):
        ctx = _ctx("Bash", {
            "command": 'curl -u admin:secret123 https://api.example.com/data',
        })
        violations = self.rule.evaluate(ctx)
        assert any("Curl" in v.message or "curl" in v.message.lower() for v in violations)

    def test_detects_curl_auth_header(self):
        ctx = _ctx("Bash", {
            "command": 'curl -H "Authorization: Bearer sk_live_abc123xyz456" https://api.example.com',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_detects_terraform_state(self):
        ctx = _ctx("Write", {
            "file_path": "terraform.tfstate",
            "content": '{"serial": 42, "lineage": "abc-123"}',
        })
        violations = self.rule.evaluate(ctx)
        assert any("Terraform" in v.message for v in violations)

    def test_detects_github_pat(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'GITHUB_TOKEN = "github_pat_11A0B1C2D3_abcdefghijklmnop"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_allows_db_connection_placeholder_password(self):
        """DB URL with 'changeme' password should not trigger."""
        ctx = _ctx("Write", {
            "file_path": "docker-compose.yml",
            "content": 'POSTGRES_URL=postgres://admin:changeme@db:5432/app',
        })
        violations = self.rule.evaluate(ctx)
        assert not any("Database connection" in v.message for v in violations)

    def test_extra_prefixes_config(self):
        """Custom prefixes from config should be detected."""
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "config.py", "content": 'key = "myco_secret_abcdef"'},
            project_dir="/tmp/project",
            config={"no-secrets": {"extra_prefixes": ["myco_secret_"]}},
        )
        violations = self.rule.evaluate(ctx)
        assert any("myco_secret_" in v.message for v in violations)

    def test_detects_npmrc_auth_token(self):
        ctx = _ctx("Write", {
            "file_path": ".npmrc",
            "content": '//registry.npmjs.org/:_authToken=npm_1234567890abcdef',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_detects_mongodb_connection(self):
        ctx = _ctx("Write", {
            "file_path": "config.py",
            "content": 'MONGO_URL = "mongodb+srv://admin:realpass123@cluster.mongodb.net/db"',
        })
        violations = self.rule.evaluate(ctx)
        assert any("Database connection" in v.message for v in violations)


# ---------------------------------------------------------------------------
# NoPushToMain
# ---------------------------------------------------------------------------


class TestNoPushToMain:
    rule = NoPushToMain()

    def test_warns_push_to_main(self):
        ctx = _ctx("Bash", {"command": "git push origin main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_warns_push_to_master(self):
        ctx = _ctx("Bash", {"command": "git push origin master"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_push_to_feature(self):
        ctx = _ctx("Bash", {"command": "git push origin feature/my-branch"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_push_with_u_flag(self):
        ctx = _ctx("Bash", {"command": "git push -u origin feature/my-branch"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_force_push_to_main(self):
        """Force pushes are handled by no-force-push, not this rule."""
        ctx = _ctx("Bash", {"command": "git push --force origin main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_bash_tool(self):
        ctx = _ctx("Write", {"file_path": "x.sh", "content": "git push origin main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_warns_push_main_case_insensitive(self):
        ctx = _ctx("Bash", {"command": "git push origin Main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_empty_command(self):
        ctx = _ctx("Bash", {"command": ""})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_pull_from_main(self):
        """git pull from main should not trigger."""
        ctx = _ctx("Bash", {"command": "git pull origin main"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# NoSkipHooks
# ---------------------------------------------------------------------------


class TestNoSkipHooks:
    rule = NoSkipHooks()

    def test_warns_no_verify(self):
        ctx = _ctx("Bash", {"command": "git commit -m 'fix' --no-verify"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_warns_no_gpg_sign(self):
        ctx = _ctx("Bash", {"command": "git commit -m 'fix' --no-gpg-sign"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_warns_both_flags(self):
        ctx = _ctx("Bash", {"command": "git commit -m 'fix' --no-verify --no-gpg-sign"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 2

    def test_allows_normal_commit(self):
        ctx = _ctx("Bash", {"command": "git commit -m 'fix bug'"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_bash_tool(self):
        ctx = _ctx("Write", {"file_path": "x.sh", "content": "git commit --no-verify"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_empty_command(self):
        ctx = _ctx("Bash", {"command": ""})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_no_verify_anywhere_in_command(self):
        ctx = _ctx("Bash", {"command": "git add . && git commit --no-verify -m 'quick'"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# NoTestWeakening
# ---------------------------------------------------------------------------


class TestNoTestWeakening:
    rule = NoTestWeakening()

    def test_detects_pytest_skip(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_auth.py",
            "content": "@pytest.mark.skip\ndef test_login():\n    pass",
        })
        violations = self.rule.evaluate(ctx)
        assert any("skip" in v.message.lower() for v in violations)

    def test_detects_unittest_skip(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_auth.py",
            "content": "@unittest.skip('broken')\ndef test_login(self):\n    pass",
        })
        violations = self.rule.evaluate(ctx)
        assert any("skip" in v.message.lower() for v in violations)

    def test_detects_jest_skip(self):
        ctx = _ctx("Write", {
            "file_path": "src/__tests__/auth.test.ts",
            "content": "it.skip('should login', () => {})",
        })
        violations = self.rule.evaluate(ctx)
        assert any("skip" in v.message.lower() for v in violations)

    def test_detects_test_skip_jest(self):
        ctx = _ctx("Write", {
            "file_path": "src/__tests__/auth.test.ts",
            "content": "test.skip('should login', () => {})",
        })
        violations = self.rule.evaluate(ctx)
        assert any("skip" in v.message.lower() for v in violations)

    def test_detects_assert_true(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_core.py",
            "content": "def test_feature():\n    assert True",
        })
        violations = self.rule.evaluate(ctx)
        assert any("assert True" in v.message for v in violations)

    def test_detects_assertTrue_True(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_core.py",
            "content": "def test_feature(self):\n    self.assertTrue(True)",
        })
        violations = self.rule.evaluate(ctx)
        assert any("assertTrue" in v.message for v in violations)

    def test_detects_expect_true_toBe_true(self):
        ctx = _ctx("Write", {
            "file_path": "src/__tests__/core.test.ts",
            "content": "expect(true).toBe(true)",
        })
        violations = self.rule.evaluate(ctx)
        assert any("expect" in v.message.lower() for v in violations)

    def test_detects_commented_assert(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_core.py",
            "content": "def test_feature():\n    # assert result == expected\n    pass",
        })
        violations = self.rule.evaluate(ctx)
        assert any("Commented-out" in v.message for v in violations)

    def test_detects_commented_expect(self):
        ctx = _ctx("Write", {
            "file_path": "src/__tests__/core.test.ts",
            "content": "// expect(result).toBe(42)",
        })
        violations = self.rule.evaluate(ctx)
        assert any("Commented-out" in v.message for v in violations)

    def test_detects_xfail_no_reason(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_core.py",
            "content": "@pytest.mark.xfail\ndef test_flaky():\n    assert False",
        })
        violations = self.rule.evaluate(ctx)
        assert any("xfail" in v.message for v in violations)

    def test_allows_xfail_with_reason(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_core.py",
            "content": "@pytest.mark.xfail(reason='known upstream bug')\ndef test_flaky():\n    assert False",
        })
        violations = self.rule.evaluate(ctx)
        assert not any("xfail" in v.message for v in violations)

    def test_detects_empty_test_function(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_core.py",
            "content": "def test_placeholder(self):\n    pass",
        })
        violations = self.rule.evaluate(ctx)
        assert any("Empty test" in v.message for v in violations)

    def test_ignores_non_test_file(self):
        ctx = _ctx("Write", {
            "file_path": "src/utils.py",
            "content": "assert True",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_write_tool(self):
        ctx = _ctx("Bash", {
            "command": "echo 'assert True' > tests/test_core.py",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_in_spec_file(self):
        ctx = _ctx("Write", {
            "file_path": "spec_helper.py",
            "content": "@pytest.mark.skip\ndef test_something():\n    pass",
        })
        violations = self.rule.evaluate(ctx)
        assert any("skip" in v.message.lower() for v in violations)

    def test_detects_describe_skip_jest(self):
        ctx = _ctx("Write", {
            "file_path": "src/__tests__/auth.spec.ts",
            "content": "describe.skip('auth', () => {})",
        })
        violations = self.rule.evaluate(ctx)
        assert any("skip" in v.message.lower() for v in violations)

    def test_ignores_empty_content_in_test_file(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_core.py",
            "content": "",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_meaningful_test(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_core.py",
            "content": "def test_addition():\n    assert 1 + 1 == 2",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_multiple_violations(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_core.py",
            "content": "@pytest.mark.skip\ndef test_one():\n    assert True\n    # assert result == 42",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 3  # skip + assert True + commented assert


# ---------------------------------------------------------------------------
# Pack loader
# ---------------------------------------------------------------------------


class TestPackLoader:
    def test_load_universal_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["universal"])
        assert len(rules) == 15  # 14 original + git-checkpoint
        ids = {r.id for r in rules}
        assert "no-secrets" in ids
        assert "no-env-commit" in ids
        assert "no-force-push" in ids
        assert "no-push-to-main" in ids
        assert "no-skip-hooks" in ids
        assert "no-destructive-commands" in ids
        assert "dependency-hygiene" in ids
        assert "no-test-weakening" in ids
        assert "max-file-size" in ids
        assert "drift-detector" in ids
        assert "no-debug-artifacts" in ids
        assert "no-todo-left" in ids
        assert "test-with-changes" in ids

    def test_load_unknown_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["nonexistent"])
        assert rules == []
