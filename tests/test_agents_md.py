"""Tests for AGENTS.md parser and config mapper."""
from __future__ import annotations

from click.testing import CliRunner

from agentlint.agents_md import (
    find_agents_md,
    generate_config,
    map_to_config,
    merge_with_existing,
    parse_agents_md,
)
from agentlint.cli import main
from agentlint.detector import detect_stack


# ---------------------------------------------------------------------------
# find_agents_md
# ---------------------------------------------------------------------------


class TestFindAgentsMd:
    def test_finds_uppercase(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# Agents")
        result = find_agents_md(str(tmp_path))
        assert result is not None
        assert result.name == "AGENTS.md"

    def test_finds_lowercase(self, tmp_path):
        (tmp_path / "agents.md").write_text("# Agents")
        result = find_agents_md(str(tmp_path))
        assert result is not None
        # On case-insensitive filesystems, agents.md may resolve as AGENTS.md.
        assert result.name.lower() == "agents.md"

    def test_finds_titlecase(self, tmp_path):
        (tmp_path / "Agents.md").write_text("# Agents")
        result = find_agents_md(str(tmp_path))
        assert result is not None
        assert result.name.lower() == "agents.md"

    def test_prefers_uppercase(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# upper")
        result = find_agents_md(str(tmp_path))
        assert result is not None
        assert result.name.lower() == "agents.md"

    def test_returns_none_when_missing(self, tmp_path):
        result = find_agents_md(str(tmp_path))
        assert result is None


# ---------------------------------------------------------------------------
# parse_agents_md
# ---------------------------------------------------------------------------


class TestParseAgentsMd:
    def test_parses_h2_sections(self, tmp_path):
        md = "## Testing\nRun pytest\n## Security\nNever commit secrets\n"
        f = tmp_path / "AGENTS.md"
        f.write_text(md)
        sections = parse_agents_md(f)
        assert "Testing" in sections
        assert "Run pytest" in sections["Testing"]
        assert "Security" in sections
        assert "Never commit secrets" in sections["Security"]

    def test_parses_h3_sections(self, tmp_path):
        md = "### Code Style\nUse black\n### Imports\nSort with isort\n"
        f = tmp_path / "AGENTS.md"
        f.write_text(md)
        sections = parse_agents_md(f)
        assert "Code Style" in sections
        assert "Imports" in sections

    def test_mixed_h2_h3(self, tmp_path):
        md = "## Overview\nProject info\n### Details\nMore info\n## Testing\nRun tests\n"
        f = tmp_path / "AGENTS.md"
        f.write_text(md)
        sections = parse_agents_md(f)
        assert "Overview" in sections
        assert "Details" in sections
        assert "Testing" in sections

    def test_empty_file(self, tmp_path):
        f = tmp_path / "AGENTS.md"
        f.write_text("")
        sections = parse_agents_md(f)
        assert sections == {}

    def test_no_headings(self, tmp_path):
        f = tmp_path / "AGENTS.md"
        f.write_text("Just some text without headings.\nAnother line.\n")
        sections = parse_agents_md(f)
        assert sections == {}

    def test_ignores_h1(self, tmp_path):
        md = "# Title\nIntro text\n## Section\nBody\n"
        f = tmp_path / "AGENTS.md"
        f.write_text(md)
        sections = parse_agents_md(f)
        assert "Title" not in sections
        assert "Section" in sections

    def test_multiline_body(self, tmp_path):
        md = "## Testing\nLine 1\nLine 2\nLine 3\n"
        f = tmp_path / "AGENTS.md"
        f.write_text(md)
        sections = parse_agents_md(f)
        assert "Line 1" in sections["Testing"]
        assert "Line 3" in sections["Testing"]

    def test_heading_with_extra_spaces(self, tmp_path):
        md = "##   Spaced Heading  \nBody text\n"
        f = tmp_path / "AGENTS.md"
        f.write_text(md)
        sections = parse_agents_md(f)
        assert "Spaced Heading" in sections

    def test_nonexistent_file(self, tmp_path):
        sections = parse_agents_md(tmp_path / "nope.md")
        assert sections == {}


# ---------------------------------------------------------------------------
# map_to_config
# ---------------------------------------------------------------------------


class TestMapToConfig:
    def test_detects_python_pack(self):
        sections = {"Development": "Use Python 3.11 with pytest for testing"}
        config = map_to_config(sections)
        assert "python" in config["packs"]

    def test_detects_frontend_pack(self):
        sections = {"Stack": "Frontend built with TypeScript and webpack"}
        config = map_to_config(sections)
        assert "frontend" in config["packs"]

    def test_detects_react_pack(self):
        sections = {"Stack": "UI built with React and JSX components"}
        config = map_to_config(sections)
        assert "react" in config["packs"]

    def test_detects_seo_pack(self):
        sections = {"SEO": "All pages must have meta tags and open graph data"}
        config = map_to_config(sections)
        assert "seo" in config["packs"]

    def test_detects_security_pack(self):
        sections = {"Security": "Never commit secrets or API keys"}
        config = map_to_config(sections)
        assert "security" in config["packs"]

    def test_detects_no_env_commit_rule(self):
        sections = {"Files": "Never commit .env files to the repository"}
        config = map_to_config(sections)
        assert "no-env-commit" in config["rules"]

    def test_detects_commit_message_rule(self):
        sections = {"Git": "Use conventional commit messages for all commits"}
        config = map_to_config(sections)
        assert "commit-message-format" in config["rules"]

    def test_detects_no_secrets_rule(self):
        sections = {"Security": "Never hardcode API key values in source code"}
        config = map_to_config(sections)
        assert "no-secrets" in config["rules"]

    def test_detects_drift_detector_with_testing(self):
        sections = {"Testing": "Always run pytest after changes"}
        config = map_to_config(sections)
        assert "drift-detector" in config["rules"]

    def test_always_includes_universal_and_quality(self):
        sections = {"Random": "Nothing useful here"}
        config = map_to_config(sections)
        assert "universal" in config["packs"]
        assert "quality" in config["packs"]

    def test_empty_sections(self):
        config = map_to_config({})
        assert config["packs"] == ["quality", "universal"]
        assert config["rules"] == {}

    def test_multiple_packs_detected(self):
        sections = {
            "Stack": "Python backend with React frontend",
            "Security": "Never expose credentials",
        }
        config = map_to_config(sections)
        assert "python" in config["packs"]
        assert "react" in config["packs"]
        assert "security" in config["packs"]


# ---------------------------------------------------------------------------
# generate_config
# ---------------------------------------------------------------------------


class TestGenerateConfig:
    def test_generates_valid_yaml(self):
        import yaml

        mapped = {"packs": ["universal", "quality", "python"], "rules": {}}
        output = generate_config(mapped)
        parsed = yaml.safe_load(output)
        assert parsed["packs"] == ["universal", "quality", "python"]

    def test_includes_header(self):
        mapped = {"packs": ["universal"], "rules": {}}
        output = generate_config(mapped)
        assert "Generated from AGENTS.md" in output

    def test_includes_rules_when_present(self):
        mapped = {
            "packs": ["universal"],
            "rules": {"no-secrets": {"enabled": True}},
        }
        output = generate_config(mapped)
        assert "no-secrets" in output

    def test_defaults_to_standard_severity(self):
        import yaml

        mapped = {"packs": ["universal"], "rules": {}}
        output = generate_config(mapped)
        parsed = yaml.safe_load(output)
        assert parsed["severity"] == "standard"


# ---------------------------------------------------------------------------
# merge_with_existing
# ---------------------------------------------------------------------------


class TestMergeWithExisting:
    def test_adds_new_packs(self):
        import yaml

        existing = "packs:\n  - universal\n  - quality\nrules: {}\n"
        mapped = {"packs": ["universal", "quality", "python"], "rules": {}}
        result = merge_with_existing(existing, mapped)
        parsed = yaml.safe_load(result)
        assert "python" in parsed["packs"]

    def test_preserves_existing_packs(self):
        import yaml

        existing = "packs:\n  - universal\n  - security\nrules: {}\n"
        mapped = {"packs": ["universal", "python"], "rules": {}}
        result = merge_with_existing(existing, mapped)
        parsed = yaml.safe_load(result)
        assert "security" in parsed["packs"]
        assert "python" in parsed["packs"]

    def test_does_not_overwrite_existing_rules(self):
        import yaml

        existing = "packs:\n  - universal\nrules:\n  no-secrets:\n    severity: error\n"
        mapped = {"packs": ["universal"], "rules": {"no-secrets": {"enabled": True}}}
        result = merge_with_existing(existing, mapped)
        parsed = yaml.safe_load(result)
        assert parsed["rules"]["no-secrets"]["severity"] == "error"

    def test_adds_new_rules(self):
        import yaml

        existing = "packs:\n  - universal\nrules: {}\n"
        mapped = {"packs": ["universal"], "rules": {"drift-detector": {"threshold": 3}}}
        result = merge_with_existing(existing, mapped)
        parsed = yaml.safe_load(result)
        assert "drift-detector" in parsed["rules"]

    def test_handles_malformed_existing_yaml(self):
        import yaml

        existing = "{{{not valid yaml"
        mapped = {"packs": ["universal", "python"], "rules": {}}
        result = merge_with_existing(existing, mapped)
        parsed = yaml.safe_load(result)
        assert "python" in parsed["packs"]

    def test_includes_header(self):
        existing = "packs:\n  - universal\n"
        mapped = {"packs": ["universal"], "rules": {}}
        result = merge_with_existing(existing, mapped)
        assert "Updated with conventions from AGENTS.md" in result


# ---------------------------------------------------------------------------
# CLI: import-agents-md
# ---------------------------------------------------------------------------


class TestImportAgentsMdCLI:
    def test_no_agents_md_exits_1(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["import-agents-md", "--project-dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "No AGENTS.md found" in result.output

    def test_empty_agents_md_exits_1(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("")
        runner = CliRunner()
        result = runner.invoke(main, ["import-agents-md", "--project-dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "empty" in result.output.lower()

    def test_dry_run_does_not_write(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("## Testing\nRun pytest\n")
        runner = CliRunner()
        result = runner.invoke(
            main, ["import-agents-md", "--project-dir", str(tmp_path), "--dry-run"]
        )
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()
        assert not (tmp_path / "agentlint.yml").exists()

    def test_writes_config(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("## Security\nNever commit secrets\n")
        runner = CliRunner()
        result = runner.invoke(main, ["import-agents-md", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "agentlint.yml").exists()
        content = (tmp_path / "agentlint.yml").read_text()
        assert "security" in content

    def test_merge_with_existing(self, tmp_path):
        (tmp_path / "agentlint.yml").write_text(
            "packs:\n  - universal\n  - quality\nrules: {}\n"
        )
        (tmp_path / "AGENTS.md").write_text("## Python\nUse pytest for testing\n")
        runner = CliRunner()
        result = runner.invoke(
            main, ["import-agents-md", "--project-dir", str(tmp_path), "--merge"]
        )
        assert result.exit_code == 0
        content = (tmp_path / "agentlint.yml").read_text()
        assert "python" in content
        assert "universal" in content

    def test_shows_detected_packs(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("## Stack\nPython backend with React\n")
        runner = CliRunner()
        result = runner.invoke(
            main, ["import-agents-md", "--project-dir", str(tmp_path), "--dry-run"]
        )
        assert result.exit_code == 0
        assert "python" in result.output.lower()
        assert "react" in result.output.lower()


# ---------------------------------------------------------------------------
# Detector integration
# ---------------------------------------------------------------------------


class TestDetectorAgentsMdIntegration:
    def test_agents_md_adds_security_pack(self, tmp_path):
        """AGENTS.md with security keywords should add security to detected packs."""
        (tmp_path / "AGENTS.md").write_text("## Security\nNever expose credentials\n")
        result = detect_stack(str(tmp_path))
        assert "security" in result

    def test_agents_md_does_not_duplicate_packs(self, tmp_path):
        """If python is already detected, AGENTS.md shouldn't add it again."""
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n")
        (tmp_path / "AGENTS.md").write_text("## Development\nUse Python 3.11\n")
        result = detect_stack(str(tmp_path))
        assert result.count("python") == 1

    def test_agents_md_absent_no_change(self, tmp_path):
        """Without AGENTS.md, detection is unchanged."""
        result = detect_stack(str(tmp_path))
        assert result == ["universal", "quality"]

    def test_agents_md_empty_no_change(self, tmp_path):
        """Empty AGENTS.md should not change detection."""
        (tmp_path / "AGENTS.md").write_text("")
        result = detect_stack(str(tmp_path))
        assert result == ["universal", "quality"]

    def test_agents_md_parse_error_handled_gracefully(self, tmp_path, monkeypatch):
        """If AGENTS.md parsing throws, detection should continue without error."""
        (tmp_path / "AGENTS.md").write_text("## Security\nNever expose credentials\n")

        def bad_parse(_path):
            raise RuntimeError("parse failed")

        monkeypatch.setattr("agentlint.agents_md.parse_agents_md", bad_parse)
        result = detect_stack(str(tmp_path))
        # Should fall back to base packs without crashing.
        assert result == ["universal", "quality"]
