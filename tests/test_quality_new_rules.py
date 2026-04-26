"""Tests for new quality rules: no-large-diff, no-file-creation-sprawl, naming-conventions."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.quality.naming_conventions import NamingConventions
from agentlint.packs.quality.no_file_creation_sprawl import NoFileCreationSprawl
from agentlint.packs.quality.no_large_diff import NoLargeDiff


def _make_context(
    tool_name: str = "Write",
    file_path: str | None = "/project/src/app.py",
    file_content: str | None = None,
    file_content_before: str | None = None,
    config: dict | None = None,
    session_state: dict | None = None,
) -> RuleContext:
    tool_input = {"file_path": file_path} if file_path else {}
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/project",
        file_content=file_content,
        file_content_before=file_content_before,
        config=config or {},
        session_state=session_state if session_state is not None else {},
    )


# === no-large-diff ===

class TestNoLargeDiff:
    def test_small_edit_passes(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 50,
            file_content_before="line\n" * 40,
        )
        assert rule.evaluate(ctx) == []

    def test_large_addition_warns(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 300,
            file_content_before="line\n" * 10,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "290 lines added" in violations[0].message

    def test_large_removal_warns(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 10,
            file_content_before="line\n" * 200,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "190 lines removed" in violations[0].message

    def test_new_file_counts_as_addition(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 300,
            file_content_before=None,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "300 lines added" in violations[0].message

    def test_custom_thresholds(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 60,
            file_content_before="line\n" * 10,
            config={"no-large-diff": {"max_lines_added": 30}},
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_default_threshold_200(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 201,
            file_content_before="",
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_exactly_at_threshold_passes(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_content="line\n" * 200,
            file_content_before="",
        )
        assert rule.evaluate(ctx) == []

    def test_non_write_edit_ignored(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            tool_name="Bash",
            file_content="line\n" * 500,
            file_content_before="",
        )
        assert rule.evaluate(ctx) == []

    def test_no_file_content_passes(self):
        rule = NoLargeDiff()
        ctx = _make_context(file_content=None)
        assert rule.evaluate(ctx) == []

    def test_edit_tool_checked(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            tool_name="Edit",
            file_content="line\n" * 300,
            file_content_before="line\n" * 10,
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_test_file_exempt_by_default(self):
        """Test files should not trigger no-large-diff."""
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/tests/test_auth.py",
            file_content="line\n" * 500,
            file_content_before="",
        )
        assert rule.evaluate(ctx) == []

    def test_test_file_patterns(self):
        """Various test file naming conventions should all be exempt."""
        rule = NoLargeDiff()
        test_paths = [
            "/project/tests/test_models.py",        # test_ prefix
            "/project/src/auth_test.go",             # _test suffix
            "/project/src/Button.spec.tsx",          # .spec.
            "/project/src/api.test.ts",              # .test.
            "/project/tests/conftest.py",            # conftest
            "/project/spec/models_spec.rb",          # _spec suffix
        ]
        for path in test_paths:
            ctx = _make_context(
                file_path=path,
                file_content="line\n" * 500,
                file_content_before="",
            )
            assert rule.evaluate(ctx) == [], f"Should exempt: {path}"

    def test_non_test_file_still_triggers(self):
        """Regular source files should still trigger the rule."""
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/src/app.py",
            file_content="line\n" * 300,
            file_content_before="",
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_exempt_test_files_disabled(self):
        """Config can disable test file exemption."""
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/tests/test_big.py",
            file_content="line\n" * 500,
            file_content_before="",
            config={"no-large-diff": {"exempt_test_files": False}},
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_custom_test_patterns(self):
        """Custom test_file_patterns should override defaults."""
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/checks/check_auth.py",
            file_content="line\n" * 500,
            file_content_before="",
            config={"no-large-diff": {"test_file_patterns": ["check_*"]}},
        )
        assert rule.evaluate(ctx) == []

    # --- v1.9.0: non-code file exemption tests ---

    def test_md_file_exempt(self):
        """Markdown files should be exempt from no-large-diff."""
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/docs/README.md",
            file_content="line\n" * 500,
            file_content_before="",
        )
        assert rule.evaluate(ctx) == []

    def test_yml_file_exempt(self):
        """YAML files should be exempt from no-large-diff."""
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/config/deploy.yml",
            file_content="line\n" * 500,
            file_content_before="",
        )
        assert rule.evaluate(ctx) == []

    def test_json_file_exempt(self):
        """JSON files should be exempt from no-large-diff."""
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/data/fixtures.json",
            file_content="line\n" * 500,
            file_content_before="",
        )
        assert rule.evaluate(ctx) == []

    def test_txt_file_exempt(self):
        """Text files should be exempt from no-large-diff."""
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/notes/todo.txt",
            file_content="line\n" * 500,
            file_content_before="",
        )
        assert rule.evaluate(ctx) == []

    def test_py_file_still_checked(self):
        """Python files should still trigger no-large-diff."""
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/src/app.py",
            file_content="line\n" * 500,
            file_content_before="",
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_ts_file_still_checked(self):
        """TypeScript files should still trigger no-large-diff."""
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/src/app.ts",
            file_content="line\n" * 500,
            file_content_before="",
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_tsx_file_still_checked(self):
        """TSX files should still trigger no-large-diff."""
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/src/Component.tsx",
            file_content="line\n" * 500,
            file_content_before="",
        )
        assert len(rule.evaluate(ctx)) == 1

    def test_custom_extensions(self):
        """Config extensions: ['.py'] should only check .py, exempt .ts."""
        rule = NoLargeDiff()
        # .ts should be exempt when only .py is in extensions
        ctx_ts = _make_context(
            file_path="/project/src/app.ts",
            file_content="line\n" * 500,
            file_content_before="",
            config={"no-large-diff": {"extensions": [".py"]}},
        )
        assert rule.evaluate(ctx_ts) == []

        # .py should still be checked
        ctx_py = _make_context(
            file_path="/project/src/app.py",
            file_content="line\n" * 500,
            file_content_before="",
            config={"no-large-diff": {"extensions": [".py"]}},
        )
        assert len(rule.evaluate(ctx_py)) == 1


class TestNoLargeDiffMigrationExempt:
    """v1.10.0: Alembic / Rails / migrations/versions/ are single-unit migrations."""

    def test_alembic_migration_exempt(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/alembic/versions/abc_add_columns.py",
            file_content="line\n" * 250,
            file_content_before=None,
        )
        assert rule.evaluate(ctx) == []

    def test_migrations_versions_exempt(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/migrations/versions/001_init.py",
            file_content="line\n" * 250,
            file_content_before=None,
        )
        assert rule.evaluate(ctx) == []

    def test_rails_db_migrate_exempt(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/db/migrate/20260101_add_users.rb",
            file_content="line\n" * 250,
            file_content_before=None,
        )
        # .rb is a code extension; the migration path exemption should kick in.
        assert rule.evaluate(ctx) == []

    def test_non_migration_path_still_checked(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/src/migrate.py",  # the word "migrate" but not in versions/
            file_content="line\n" * 300,
            file_content_before=None,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_global_migration_paths_config_extends(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/custom_db_changes/004_alter.py",
            file_content="line\n" * 250,
            file_content_before=None,
            config={"migration_paths": ["custom_db_changes/"]},
        )
        assert rule.evaluate(ctx) == []

    def test_per_rule_migration_paths_config_extends(self):
        rule = NoLargeDiff()
        ctx = _make_context(
            file_path="/project/schema_changes/v005.py",
            file_content="line\n" * 250,
            file_content_before=None,
            config={"no-large-diff": {"migration_paths": ["schema_changes/"]}},
        )
        assert rule.evaluate(ctx) == []


# === no-file-creation-sprawl ===

class TestNoFileCreationSprawl:
    def test_first_file_passes(self):
        rule = NoFileCreationSprawl()
        ctx = _make_context(
            file_path="/project/src/new.py",
            file_content_before=None,
            session_state={},
        )
        assert rule.evaluate(ctx) == []

    def test_warns_after_threshold(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(10)]}
        ctx = _make_context(
            file_path="/project/f10.py",
            file_content_before=None,
            session_state=state,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "11 new files" in violations[0].message

    def test_editing_existing_file_not_counted(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(10)]}
        ctx = _make_context(
            file_path="/project/existing.py",
            file_content_before="old content",  # exists = not new
            session_state=state,
        )
        assert rule.evaluate(ctx) == []

    def test_custom_threshold(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(3)]}
        ctx = _make_context(
            file_path="/project/f3.py",
            file_content_before=None,
            config={"no-file-creation-sprawl": {"max_new_files": 3}},
            session_state=state,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_non_write_tool_ignored(self):
        rule = NoFileCreationSprawl()
        ctx = _make_context(tool_name="Edit", file_content_before=None)
        assert rule.evaluate(ctx) == []

    def test_tracks_in_session_state(self):
        rule = NoFileCreationSprawl()
        state: dict = {}
        ctx = _make_context(
            file_path="/project/new.py",
            file_content_before=None,
            session_state=state,
        )
        rule.evaluate(ctx)
        assert "/project/new.py" in state["files_created"]

    def test_no_double_counting(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": ["/project/new.py"]}
        ctx = _make_context(
            file_path="/project/new.py",
            file_content_before=None,
            session_state=state,
        )
        rule.evaluate(ctx)
        assert state["files_created"].count("/project/new.py") == 1

    def test_no_file_path_passes(self):
        rule = NoFileCreationSprawl()
        ctx = _make_context(file_path=None, file_content_before=None)
        assert rule.evaluate(ctx) == []


class TestNoFileCreationSprawlExemptPaths:
    """v1.10.0: tests/, docs/, migrations/ are exempt from sprawl counter."""

    def test_tests_directory_exempt(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(15)]}
        ctx = _make_context(
            file_path="/project/tests/test_new.py",
            file_content_before=None,
            session_state=state,
        )
        assert rule.evaluate(ctx) == []
        # Exempt files don't enter the counter at all.
        assert "/project/tests/test_new.py" not in state["files_created"]

    def test_docs_directory_exempt(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(15)]}
        ctx = _make_context(
            file_path="/project/docs/guide.md",
            file_content_before=None,
            session_state=state,
        )
        assert rule.evaluate(ctx) == []

    def test_alembic_migration_exempt(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(15)]}
        ctx = _make_context(
            file_path="/project/alembic/versions/abc_add_column.py",
            file_content_before=None,
            session_state=state,
        )
        assert rule.evaluate(ctx) == []

    def test_migrations_versions_exempt(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(15)]}
        ctx = _make_context(
            file_path="/project/migrations/versions/001_init.py",
            file_content_before=None,
            session_state=state,
        )
        assert rule.evaluate(ctx) == []

    def test_nested_tests_directory_exempt(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(15)]}
        ctx = _make_context(
            file_path="/project/backend/tests/foo_test.py",
            file_content_before=None,
            session_state=state,
        )
        assert rule.evaluate(ctx) == []

    def test_jest_tests_directory_exempt(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(15)]}
        ctx = _make_context(
            file_path="/project/src/__tests__/Foo.test.tsx",
            file_content_before=None,
            session_state=state,
        )
        assert rule.evaluate(ctx) == []

    def test_source_files_still_counted(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/src/f{i}.py" for i in range(10)]}
        ctx = _make_context(
            file_path="/project/src/eleventh.py",
            file_content_before=None,
            session_state=state,
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_user_extra_exempt_path(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(15)]}
        ctx = _make_context(
            file_path="/project/fixtures/seed.json",
            file_content_before=None,
            config={"no-file-creation-sprawl": {"exempt_paths": ["fixtures/"]}},
            session_state=state,
        )
        assert rule.evaluate(ctx) == []

    def test_user_extra_does_not_disable_defaults(self):
        rule = NoFileCreationSprawl()
        state: dict = {"files_created": [f"/project/f{i}.py" for i in range(15)]}
        ctx = _make_context(
            file_path="/project/tests/test_x.py",
            file_content_before=None,
            config={"no-file-creation-sprawl": {"exempt_paths": ["fixtures/"]}},
            session_state=state,
        )
        # tests/ default exempt should still apply alongside user-provided fixtures/
        assert rule.evaluate(ctx) == []


# === naming-conventions ===

class TestNamingConventions:
    def _pre_context(self, file_path: str, config: dict | None = None) -> RuleContext:
        return RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": file_path},
            project_dir="/project",
            config=config or {},
        )

    def test_snake_case_python_passes(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/my_module.py")
        assert rule.evaluate(ctx) == []

    def test_camel_case_python_warns(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/MyModule.py")
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "snake_case" in violations[0].message

    def test_snake_case_ts_warns(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/my_utils.ts")
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "camelCase" in violations[0].message

    def test_camel_case_ts_passes(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/myUtils.ts")
        assert rule.evaluate(ctx) == []

    def test_pascal_case_tsx_passes(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/MyComponent.tsx")
        assert rule.evaluate(ctx) == []

    def test_snake_case_tsx_warns(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/my_component.tsx")
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert "PascalCase" in violations[0].message

    def test_init_py_exempt(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/__init__.py")
        assert rule.evaluate(ctx) == []

    def test_test_files_exempt(self):
        rule = NamingConventions()
        assert rule.evaluate(self._pre_context("/project/tests/test_app.py")) == []
        assert rule.evaluate(self._pre_context("/project/src/app.test.ts")) == []
        assert rule.evaluate(self._pre_context("/project/src/app.spec.js")) == []

    def test_unknown_extension_passes(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/data/stuff.csv")
        assert rule.evaluate(ctx) == []

    def test_custom_convention_override(self):
        rule = NamingConventions()
        ctx = self._pre_context(
            "/project/src/MyModule.py",
            config={"naming-conventions": {"python": "PascalCase"}},
        )
        assert rule.evaluate(ctx) == []

    def test_suggestion_includes_example(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/src/MyModule.py")
        violations = rule.evaluate(ctx)
        assert violations[0].suggestion is not None
        assert "my_module.py" in violations[0].suggestion

    def test_non_write_edit_ignored(self):
        rule = NamingConventions()
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"file_path": "/project/src/BadName.py"},
            project_dir="/project",
        )
        assert rule.evaluate(ctx) == []

    def test_no_file_path_passes(self):
        rule = NamingConventions()
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={},
            project_dir="/project",
        )
        assert rule.evaluate(ctx) == []

    def test_index_tsx_exempt(self):
        """index.tsx is extremely common in React — should not warn."""
        rule = NamingConventions()
        assert rule.evaluate(self._pre_context("/project/src/index.tsx")) == []
        assert rule.evaluate(self._pre_context("/project/src/index.ts")) == []
        assert rule.evaluate(self._pre_context("/project/src/index.js")) == []

    def test_kebab_case_tsx_accepted(self):
        """my-component.tsx is common in React — kebab-case should be accepted."""
        rule = NamingConventions()
        assert rule.evaluate(self._pre_context("/project/src/my-component.tsx")) == []
        assert rule.evaluate(self._pre_context("/project/src/button-group.jsx")) == []

    def test_kebab_case_ts_warns(self):
        """my-utils.ts should still warn — TS expects camelCase, not kebab-case."""
        rule = NamingConventions()
        violations = rule.evaluate(self._pre_context("/project/src/my-utils.ts"))
        assert len(violations) == 1

    def test_file_without_extension_passes(self):
        rule = NamingConventions()
        ctx = self._pre_context("/project/Makefile")
        assert rule.evaluate(ctx) == []

    def test_typescript_config_override(self):
        rule = NamingConventions()
        ctx = self._pre_context(
            "/project/src/MyUtils.ts",
            config={"naming-conventions": {"typescript": "PascalCase"}},
        )
        assert rule.evaluate(ctx) == []

    def test_react_components_config_override(self):
        rule = NamingConventions()
        ctx = self._pre_context(
            "/project/src/my_component.tsx",
            config={"naming-conventions": {"react_components": "snake_case"}},
        )
        assert rule.evaluate(ctx) == []

    def test_invalid_convention_name_passes(self):
        """Unknown convention name in config should not crash."""
        rule = NamingConventions()
        ctx = self._pre_context(
            "/project/src/app.py",
            config={"naming-conventions": {"python": "SCREAMING_CASE"}},
        )
        assert rule.evaluate(ctx) == []

    def test_suggest_name_fallback(self):
        """_suggest_name with unknown convention returns original."""
        rule = NamingConventions()
        result = rule._suggest_name("myFile", "unknown_convention", "py")
        assert result == "myFile.py"

    def test_alembic_migration_exempt(self):
        """Alembic revision files should be exempt."""
        rule = NamingConventions()
        assert rule.evaluate(self._pre_context(
            "/project/alembic/versions/92cd48a3c5f4_change_merged_from_.py",
        )) == []

    def test_migrations_versions_exempt(self):
        """Django/generic migrations should be exempt."""
        rule = NamingConventions()
        assert rule.evaluate(self._pre_context(
            "/project/migrations/versions/abc123def456_init.py",
        )) == []

    def test_regular_file_still_checked(self):
        """Non-migration files should still be checked."""
        rule = NamingConventions()
        violations = rule.evaluate(self._pre_context("/project/src/MyModule.py"))
        assert len(violations) == 1

    def test_custom_migration_paths(self):
        """Custom migration_paths config should exempt matching files."""
        rule = NamingConventions()
        ctx = self._pre_context(
            "/project/db/revisions/abc123_add_users.py",
            config={"naming-conventions": {"migration_paths": ["db/revisions"]}},
        )
        assert rule.evaluate(ctx) == []

    # --- v1.9.0: Django migration naming tests ---

    def test_django_migration_exempt(self):
        """Django migration files should be exempt (path contains 'migration')."""
        rule = NamingConventions()
        ctx = self._pre_context("/project/app/migrations/0001_initial.py")
        assert rule.evaluate(ctx) == []

    def test_django_migration_numbered_exempt(self):
        """Numbered Django migration files should be exempt."""
        rule = NamingConventions()
        ctx = self._pre_context("/project/myapp/migrations/0002_add_users.py")
        assert rule.evaluate(ctx) == []

    def test_non_migration_numeric_prefix_not_exempt(self):
        """Numeric-prefix files outside migrations should NOT be exempt."""
        rule = NamingConventions()
        violations = rule.evaluate(
            self._pre_context("/project/src/0001_config.py"),
        )
        assert len(violations) == 1
