"""Tests for Python pack PreToolUse rules."""
from __future__ import annotations

import pytest

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.python.no_sql_injection import NoSqlInjection
from agentlint.packs.python.no_bare_except import NoBareExcept
from agentlint.packs.python.no_unsafe_shell import NoUnsafeShell
from agentlint.packs.python.no_dangerous_migration import NoDangerousMigration
from agentlint.packs.python.no_wildcard_import import NoWildcardImport


def _ctx(tool_name: str, tool_input: dict, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
        config=config or {},
    )


# ---------------------------------------------------------------------------
# NoSqlInjection
# ---------------------------------------------------------------------------


class TestNoSqlInjection:
    rule = NoSqlInjection()

    def test_detects_fstring_select(self):
        ctx = _ctx("Write", {
            "file_path": "app/db.py",
            "content": 'query = f"SELECT * FROM users WHERE id = {user_id}"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR
        assert "f-string" in violations[0].message

    def test_detects_fstring_insert(self):
        ctx = _ctx("Write", {
            "file_path": "app/db.py",
            "content": "query = f'INSERT INTO users VALUES ({name})'",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_detects_format_sql(self):
        ctx = _ctx("Write", {
            "file_path": "app/db.py",
            "content": '"SELECT * FROM users WHERE id = {}".format(user_id)',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert ".format()" in violations[0].message

    def test_detects_concat_sql(self):
        ctx = _ctx("Write", {
            "file_path": "app/db.py",
            "content": 'query = "SELECT * FROM users WHERE id = " + user_id',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "concatenation" in violations[0].message

    def test_detects_percent_sql(self):
        ctx = _ctx("Write", {
            "file_path": "app/db.py",
            "content": '"SELECT * FROM users WHERE id = %s" % user_id',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "% operator" in violations[0].message

    def test_skips_test_files(self):
        ctx = _ctx("Write", {
            "file_path": "tests/test_db.py",
            "content": 'query = f"SELECT * FROM users WHERE id = {user_id}"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_sql_files(self):
        ctx = _ctx("Write", {
            "file_path": "migrations/init.sql",
            "content": "SELECT * FROM users",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_comment_lines(self):
        ctx = _ctx("Write", {
            "file_path": "app/db.py",
            "content": '# query = f"SELECT * FROM users WHERE id = {user_id}"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_parameterized_query(self):
        ctx = _ctx("Write", {
            "file_path": "app/db.py",
            "content": 'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_python_files(self):
        ctx = _ctx("Write", {
            "file_path": "app/query.js",
            "content": 'f"SELECT * FROM users"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_write_tools(self):
        ctx = _ctx("Read", {
            "file_path": "app/db.py",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_extra_keywords_config(self):
        ctx = _ctx("Write", {
            "file_path": "app/db.py",
            "content": 'query = f"MERGE INTO users"',
        }, config={"extra_keywords": ["MERGE"]})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_detects_fstring_delete(self):
        ctx = _ctx("Write", {
            "file_path": "app/db.py",
            "content": 'query = f"DELETE FROM users WHERE id = {uid}"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_detects_fstring_update(self):
        ctx = _ctx("Write", {
            "file_path": "app/db.py",
            "content": 'query = f"UPDATE users SET name = {name}"',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1


# ---------------------------------------------------------------------------
# NoBareExcept
# ---------------------------------------------------------------------------


class TestNoBareExcept:
    rule = NoBareExcept()

    def test_detects_bare_except(self):
        ctx = _ctx("Write", {
            "file_path": "app/handler.py",
            "content": "try:\n    risky()\nexcept:\n    log()",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_allows_except_exception(self):
        ctx = _ctx("Write", {
            "file_path": "app/handler.py",
            "content": "try:\n    risky()\nexcept Exception:\n    log()",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_bare_except_with_reraise(self):
        ctx = _ctx("Write", {
            "file_path": "app/handler.py",
            "content": "try:\n    risky()\nexcept:\n    log()\n    raise",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_bare_except_with_reraise_disabled(self):
        ctx = _ctx("Write", {
            "file_path": "app/handler.py",
            "content": "try:\n    risky()\nexcept:\n    log()\n    raise",
        }, config={"allow_reraise": False})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_detects_indented_bare_except(self):
        ctx = _ctx("Write", {
            "file_path": "app/handler.py",
            "content": "def foo():\n    try:\n        risky()\n    except:\n        log()",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_ignores_non_python(self):
        ctx = _ctx("Write", {
            "file_path": "app/handler.js",
            "content": "except:",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_write_tools(self):
        ctx = _ctx("Read", {"file_path": "app/handler.py"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_multiple_bare_excepts(self):
        ctx = _ctx("Write", {
            "file_path": "app/handler.py",
            "content": "try:\n    a()\nexcept:\n    b()\ntry:\n    c()\nexcept:\n    d()",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 2


# ---------------------------------------------------------------------------
# NoUnsafeShell
# ---------------------------------------------------------------------------


class TestNoUnsafeShell:
    rule = NoUnsafeShell()

    def test_detects_os_level_shell_call(self):
        """Detects os-level shell execution functions."""
        ctx = _ctx("Write", {
            "file_path": "app/deploy.py",
            "content": 'os.system("rm -rf /")',  # noqa: S605
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_detects_os_popen(self):
        ctx = _ctx("Write", {
            "file_path": "app/deploy.py",
            "content": 'result = os.popen("ls")',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_detects_subprocess_shell_true(self):
        ctx = _ctx("Write", {
            "file_path": "app/deploy.py",
            "content": 'subprocess.run("ls -la", shell=True)',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert "shell=True" in violations[0].message

    def test_detects_subprocess_call_shell_true(self):
        ctx = _ctx("Write", {
            "file_path": "app/deploy.py",
            "content": 'subprocess.call("echo hello", shell=True)',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_detects_subprocess_popen_shell_true(self):
        ctx = _ctx("Write", {
            "file_path": "app/deploy.py",
            "content": 'subprocess.Popen("echo hello", shell=True)',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_subprocess_list_args(self):
        ctx = _ctx("Write", {
            "file_path": "app/deploy.py",
            "content": 'subprocess.run(["ls", "-la"])',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_shell_true_when_configured(self):
        ctx = _ctx("Write", {
            "file_path": "app/deploy.py",
            "content": 'subprocess.run("ls -la", shell=True)',
        }, config={"allow_shell_true": True})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_skips_comment_lines(self):
        ctx = _ctx("Write", {
            "file_path": "app/deploy.py",
            "content": '# os.popen("ls")',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_python(self):
        ctx = _ctx("Write", {
            "file_path": "app/deploy.sh",
            "content": 'os.popen("ls")',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# NoDangerousMigration
# ---------------------------------------------------------------------------


class TestNoDangerousMigration:
    rule = NoDangerousMigration()

    def test_detects_drop_table_without_create(self):
        ctx = _ctx("Write", {
            "file_path": "alembic/versions/001_drop_users.py",
            "content": 'def upgrade():\n    op.drop_table("users")',
        })
        violations = self.rule.evaluate(ctx)
        assert any("drop_table" in v.message for v in violations)

    def test_allows_drop_table_with_create(self):
        ctx = _ctx("Write", {
            "file_path": "alembic/versions/001_rename.py",
            "content": 'def upgrade():\n    op.drop_table("old")\ndef downgrade():\n    op.create_table("old")',
        })
        violations = self.rule.evaluate(ctx)
        assert not any("drop_table" in v.message for v in violations)

    def test_detects_drop_column(self):
        ctx = _ctx("Write", {
            "file_path": "alembic/versions/002_remove_col.py",
            "content": 'def upgrade():\n    op.drop_column("users", "email")',
        })
        violations = self.rule.evaluate(ctx)
        assert any("drop_column" in v.message for v in violations)

    def test_detects_alter_nullable_false(self):
        ctx = _ctx("Write", {
            "file_path": "migration/003_strict.py",
            "content": 'op.alter_column("users", "name", nullable=False)',
        })
        violations = self.rule.evaluate(ctx)
        assert any("nullable=False" in v.message for v in violations)

    def test_detects_datetime_without_timezone(self):
        ctx = _ctx("Write", {
            "file_path": "alembic/versions/004_add_ts.py",
            "content": 'sa.Column("created_at", sa.DateTime)',
        })
        violations = self.rule.evaluate(ctx)
        assert any("DateTime" in v.message for v in violations)

    def test_allows_datetime_with_timezone(self):
        ctx = _ctx("Write", {
            "file_path": "alembic/versions/004_add_ts.py",
            "content": 'sa.Column("created_at", sa.DateTime(timezone=True))',
        })
        violations = self.rule.evaluate(ctx)
        assert not any("DateTime" in v.message for v in violations)

    def test_skips_non_migration_files(self):
        ctx = _ctx("Write", {
            "file_path": "app/models.py",
            "content": 'op.drop_table("users")',
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_migration_paths(self):
        ctx = _ctx("Write", {
            "file_path": "db/changes/001.py",
            "content": 'op.drop_column("users", "name")',
        }, config={"migration_paths": ["changes"]})
        violations = self.rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_datetime_timezone_config_disabled(self):
        ctx = _ctx("Write", {
            "file_path": "alembic/versions/004.py",
            "content": 'sa.Column("ts", sa.DateTime)',
        }, config={"require_timezone": False})
        violations = self.rule.evaluate(ctx)
        assert not any("DateTime" in v.message for v in violations)


# ---------------------------------------------------------------------------
# NoWildcardImport
# ---------------------------------------------------------------------------


class TestNoWildcardImport:
    rule = NoWildcardImport()

    def test_detects_wildcard_import(self):
        ctx = _ctx("Write", {
            "file_path": "app/utils.py",
            "content": "from os.path import *",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.WARNING

    def test_allows_specific_import(self):
        ctx = _ctx("Write", {
            "file_path": "app/utils.py",
            "content": "from os.path import join, exists",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_wildcard_in_init_py(self):
        ctx = _ctx("Write", {
            "file_path": "app/__init__.py",
            "content": "from app.models import *",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_allow_in(self):
        ctx = _ctx("Write", {
            "file_path": "app/compat.py",
            "content": "from os.path import *",
        }, config={"allow_in": ["compat.py"]})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_detects_multiple_wildcards(self):
        ctx = _ctx("Write", {
            "file_path": "app/utils.py",
            "content": "from os import *\nfrom sys import *",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 2

    def test_ignores_non_python(self):
        ctx = _ctx("Write", {
            "file_path": "app/utils.js",
            "content": "from os import *",
        })
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_write_tools(self):
        ctx = _ctx("Read", {"file_path": "app/utils.py"})
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# Pack loader
# ---------------------------------------------------------------------------


class TestPythonPackLoader:
    def test_load_python_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["python"])
        assert len(rules) == 6
        ids = {r.id for r in rules}
        assert "no-sql-injection" in ids
        assert "no-bare-except" in ids
        assert "no-unsafe-shell" in ids
        assert "no-dangerous-migration" in ids
        assert "no-wildcard-import" in ids
        assert "no-unnecessary-async" in ids

    def test_all_rules_have_python_pack(self):
        from agentlint.packs import load_rules

        rules = load_rules(["python"])
        for rule in rules:
            assert rule.pack == "python"
