# AgentLint Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the AgentLint core engine, universal rule pack, and Claude Code plugin — a working MVP that can be installed and immediately start validating agent behavior.

**Architecture:** Python package (pip-installable) with a CLI entry point. Claude Code plugin wraps thin shell hooks that pipe stdin to the CLI. Rules are Python classes implementing a common interface. Config via YAML with auto-detection fallback.

**Tech Stack:** Python 3.11+, click (CLI), PyYAML (config), pytest (testing), uv (package management)

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/agentlint/__init__.py`
- Create: `tests/__init__.py`
- Create: `.python-version`
- Create: `LICENSE`

**Step 1: Initialize uv project**

```bash
cd /Users/maupr92/Projects/agentlint
uv init --lib --name agentlint
```

If uv already created pyproject.toml, replace its contents. Otherwise create it:

```toml
[project]
name = "agentlint"
version = "0.1.0"
description = "Real-time quality guardrails for AI coding agents"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [
    { name = "maupr92" }
]
keywords = ["claude-code", "ai-agents", "guardrails", "linting", "hooks"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Quality Assurance",
]

dependencies = [
    "click>=8.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[project.scripts]
agentlint = "agentlint.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/agentlint"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

**Step 2: Create package init**

```python
# src/agentlint/__init__.py
"""AgentLint - Real-time quality guardrails for AI coding agents."""

__version__ = "0.1.0"
```

**Step 3: Create test directory**

```python
# tests/__init__.py
```

**Step 4: Create LICENSE (MIT)**

Standard MIT license with maupr92 as author.

**Step 5: Install dependencies and verify**

```bash
cd /Users/maupr92/Projects/agentlint
uv sync --dev
uv run python -c "import agentlint; print(agentlint.__version__)"
```

Expected: `0.1.0`

**Step 6: Commit**

```bash
git add pyproject.toml src/ tests/ LICENSE .python-version uv.lock
git commit -m "feat: scaffold agentlint Python package with uv"
```

---

### Task 2: Core Models — Rule, Violation, RuleContext

**Files:**
- Create: `src/agentlint/models.py`
- Create: `tests/test_models.py`

**Step 1: Write the failing tests**

```python
# tests/test_models.py
"""Tests for core AgentLint models."""
import pytest
from agentlint.models import (
    HookEvent,
    Rule,
    RuleContext,
    Severity,
    Violation,
)


class TestSeverity:
    def test_severity_values(self):
        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"

    def test_severity_is_blocking(self):
        assert Severity.ERROR.is_blocking is True
        assert Severity.WARNING.is_blocking is False
        assert Severity.INFO.is_blocking is False


class TestHookEvent:
    def test_hook_event_values(self):
        assert HookEvent.PRE_TOOL_USE.value == "PreToolUse"
        assert HookEvent.POST_TOOL_USE.value == "PostToolUse"
        assert HookEvent.STOP.value == "Stop"
        assert HookEvent.SESSION_START.value == "SessionStart"

    def test_from_string(self):
        assert HookEvent.from_string("PreToolUse") == HookEvent.PRE_TOOL_USE
        assert HookEvent.from_string("Stop") == HookEvent.STOP

    def test_from_string_invalid_raises(self):
        with pytest.raises(ValueError, match="Unknown hook event"):
            HookEvent.from_string("InvalidEvent")


class TestViolation:
    def test_create_violation(self):
        v = Violation(
            rule_id="no-secrets",
            message="API key detected",
            severity=Severity.ERROR,
            file_path="/tmp/config.py",
            line=23,
            suggestion="Use environment variables instead",
        )
        assert v.rule_id == "no-secrets"
        assert v.severity == Severity.ERROR
        assert v.line == 23

    def test_violation_optional_fields(self):
        v = Violation(
            rule_id="test-rule",
            message="Something wrong",
            severity=Severity.WARNING,
        )
        assert v.file_path is None
        assert v.line is None
        assert v.suggestion is None

    def test_violation_to_dict(self):
        v = Violation(
            rule_id="no-secrets",
            message="API key detected",
            severity=Severity.ERROR,
            file_path="/tmp/config.py",
            line=23,
            suggestion="Use env vars",
        )
        d = v.to_dict()
        assert d["rule_id"] == "no-secrets"
        assert d["severity"] == "error"
        assert d["line"] == 23


class TestRuleContext:
    def test_create_context(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "/tmp/foo.py", "content": "x = 1"},
            project_dir="/tmp/project",
        )
        assert ctx.tool_name == "Write"
        assert ctx.file_path == "/tmp/foo.py"
        assert ctx.session_state == {}

    def test_context_extracts_file_path_from_tool_input(self):
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Edit",
            tool_input={"file_path": "/tmp/bar.ts"},
            project_dir="/tmp/project",
        )
        assert ctx.file_path == "/tmp/bar.ts"

    def test_context_extracts_command_from_bash(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "git push --force"},
            project_dir="/tmp/project",
        )
        assert ctx.command == "git push --force"
        assert ctx.file_path is None

    def test_context_file_content_none_by_default(self):
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "/tmp/foo.py", "content": "x = 1"},
            project_dir="/tmp/project",
        )
        assert ctx.file_content is None

    def test_context_with_file_content(self):
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "/tmp/foo.py"},
            project_dir="/tmp/project",
            file_content="print('hello')",
        )
        assert ctx.file_content == "print('hello')"


class TestRule:
    def test_rule_is_abstract(self):
        with pytest.raises(TypeError):
            Rule()

    def test_concrete_rule(self):
        class MyRule(Rule):
            id = "test-rule"
            description = "A test rule"
            severity = Severity.WARNING
            events = [HookEvent.PRE_TOOL_USE]
            pack = "test"

            def evaluate(self, context: RuleContext) -> list[Violation]:
                return []

        rule = MyRule()
        assert rule.id == "test-rule"
        assert rule.pack == "test"

    def test_rule_evaluate_returns_violations(self):
        class AlwaysFailRule(Rule):
            id = "always-fail"
            description = "Always fails"
            severity = Severity.ERROR
            events = [HookEvent.PRE_TOOL_USE]
            pack = "test"

            def evaluate(self, context: RuleContext) -> list[Violation]:
                return [
                    Violation(
                        rule_id=self.id,
                        message="Always fails",
                        severity=self.severity,
                    )
                ]

        rule = AlwaysFailRule()
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "echo hi"},
            project_dir="/tmp",
        )
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].rule_id == "always-fail"

    def test_rule_matches_event(self):
        class PreOnlyRule(Rule):
            id = "pre-only"
            description = "Pre only"
            severity = Severity.WARNING
            events = [HookEvent.PRE_TOOL_USE]
            pack = "test"

            def evaluate(self, context):
                return []

        rule = PreOnlyRule()
        assert rule.matches_event(HookEvent.PRE_TOOL_USE) is True
        assert rule.matches_event(HookEvent.POST_TOOL_USE) is False
        assert rule.matches_event(HookEvent.STOP) is False
```

**Step 2: Run tests to verify they fail**

```bash
cd /Users/maupr92/Projects/agentlint
uv run pytest tests/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'agentlint.models'`

**Step 3: Implement the models**

```python
# src/agentlint/models.py
"""Core models for AgentLint."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class Severity(Enum):
    """Rule violation severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def is_blocking(self) -> bool:
        return self == Severity.ERROR


class HookEvent(Enum):
    """Claude Code hook lifecycle events."""

    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    STOP = "Stop"
    SESSION_START = "SessionStart"

    @classmethod
    def from_string(cls, value: str) -> HookEvent:
        for member in cls:
            if member.value == value:
                return member
        raise ValueError(f"Unknown hook event: {value}")


@dataclass
class Violation:
    """A single rule violation."""

    rule_id: str
    message: str
    severity: Severity
    file_path: str | None = None
    line: int | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "message": self.message,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line": self.line,
            "suggestion": self.suggestion,
        }


@dataclass
class RuleContext:
    """Context passed to rules during evaluation."""

    event: HookEvent
    tool_name: str
    tool_input: dict
    project_dir: str
    file_content: str | None = None
    config: dict = field(default_factory=dict)
    session_state: dict = field(default_factory=dict)

    @property
    def file_path(self) -> str | None:
        return self.tool_input.get("file_path")

    @property
    def command(self) -> str | None:
        return self.tool_input.get("command")


class Rule(ABC):
    """Base class for all AgentLint rules."""

    id: str
    description: str
    severity: Severity
    events: list[HookEvent]
    pack: str

    @abstractmethod
    def evaluate(self, context: RuleContext) -> list[Violation]:
        """Evaluate this rule against the given context."""

    def matches_event(self, event: HookEvent) -> bool:
        """Check if this rule should run for the given event."""
        return event in self.events
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_models.py -v
```

Expected: All tests PASS

**Step 5: Update __init__.py exports**

```python
# src/agentlint/__init__.py
"""AgentLint - Real-time quality guardrails for AI coding agents."""

__version__ = "0.1.0"

from agentlint.models import (
    HookEvent,
    Rule,
    RuleContext,
    Severity,
    Violation,
)

__all__ = [
    "HookEvent",
    "Rule",
    "RuleContext",
    "Severity",
    "Violation",
]
```

**Step 6: Commit**

```bash
git add src/agentlint/models.py src/agentlint/__init__.py tests/test_models.py
git commit -m "feat: add core models — Rule, Violation, RuleContext, Severity, HookEvent"
```

---

### Task 3: Config Parser + Stack Auto-Detection

**Files:**
- Create: `src/agentlint/config.py`
- Create: `src/agentlint/detector.py`
- Create: `tests/test_config.py`
- Create: `tests/test_detector.py`
- Create: `tests/fixtures/` (sample project files)

**Step 1: Write failing tests for detector**

```python
# tests/test_detector.py
"""Tests for stack auto-detection."""
import json
from pathlib import Path

import pytest

from agentlint.detector import detect_stack


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory."""
    return tmp_path


class TestDetectStack:
    def test_empty_project_returns_universal_only(self, tmp_project):
        packs = detect_stack(str(tmp_project))
        assert packs == ["universal"]

    def test_detects_python_from_pyproject_toml(self, tmp_project):
        (tmp_project / "pyproject.toml").write_text("[project]\nname = 'foo'")
        packs = detect_stack(str(tmp_project))
        assert "universal" in packs
        assert "python" in packs

    def test_detects_python_from_setup_py(self, tmp_project):
        (tmp_project / "setup.py").write_text("from setuptools import setup")
        packs = detect_stack(str(tmp_project))
        assert "python" in packs

    def test_detects_react_from_package_json(self, tmp_project):
        pkg = {"dependencies": {"react": "^18.0.0"}}
        (tmp_project / "package.json").write_text(json.dumps(pkg))
        packs = detect_stack(str(tmp_project))
        assert "universal" in packs
        assert "react" in packs

    def test_does_not_detect_react_without_dependency(self, tmp_project):
        pkg = {"dependencies": {"express": "^4.0.0"}}
        (tmp_project / "package.json").write_text(json.dumps(pkg))
        packs = detect_stack(str(tmp_project))
        assert "react" not in packs

    def test_detects_multiple_stacks(self, tmp_project):
        (tmp_project / "pyproject.toml").write_text("[project]\nname = 'foo'")
        pkg = {"dependencies": {"react": "^18.0.0"}}
        (tmp_project / "package.json").write_text(json.dumps(pkg))
        packs = detect_stack(str(tmp_project))
        assert set(packs) == {"universal", "python", "react"}

    def test_universal_always_first(self, tmp_project):
        (tmp_project / "pyproject.toml").write_text("[project]\nname = 'foo'")
        packs = detect_stack(str(tmp_project))
        assert packs[0] == "universal"
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_detector.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement detector**

```python
# src/agentlint/detector.py
"""Stack auto-detection for AgentLint."""
from __future__ import annotations

import json
from pathlib import Path


def detect_stack(project_dir: str) -> list[str]:
    """Detect the tech stack of a project by scanning for config files.

    Returns a list of pack names to activate, always starting with 'universal'.
    """
    root = Path(project_dir)
    packs = ["universal"]

    if _has_python(root):
        packs.append("python")

    if _has_react(root):
        packs.append("react")

    return packs


def _has_python(root: Path) -> bool:
    return (root / "pyproject.toml").exists() or (root / "setup.py").exists()


def _has_react(root: Path) -> bool:
    package_json = root / "package.json"
    if not package_json.exists():
        return False
    try:
        data = json.loads(package_json.read_text())
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        return "react" in deps
    except (json.JSONDecodeError, OSError):
        return False
```

**Step 4: Run detector tests**

```bash
uv run pytest tests/test_detector.py -v
```

Expected: All PASS

**Step 5: Write failing tests for config**

```python
# tests/test_config.py
"""Tests for AgentLint config parsing."""
from pathlib import Path

import pytest

from agentlint.config import AgentLintConfig, load_config


@pytest.fixture
def tmp_project(tmp_path):
    return tmp_path


class TestLoadConfig:
    def test_default_config_when_no_file(self, tmp_project):
        config = load_config(str(tmp_project))
        assert config.severity == "standard"
        assert "universal" in config.packs
        assert config.rules == {}

    def test_loads_from_agentlint_yml(self, tmp_project):
        yml = tmp_project / "agentlint.yml"
        yml.write_text(
            "severity: strict\npacks:\n  - universal\n  - python\nrules:\n  no-secrets:\n    severity: error\n"
        )
        config = load_config(str(tmp_project))
        assert config.severity == "strict"
        assert config.packs == ["universal", "python"]
        assert config.rules["no-secrets"]["severity"] == "error"

    def test_auto_detect_when_stack_is_auto(self, tmp_project):
        yml = tmp_project / "agentlint.yml"
        yml.write_text("stack: auto\n")
        (tmp_project / "pyproject.toml").write_text("[project]\nname = 'foo'")
        config = load_config(str(tmp_project))
        assert "python" in config.packs

    def test_explicit_packs_override_auto_detect(self, tmp_project):
        yml = tmp_project / "agentlint.yml"
        yml.write_text("packs:\n  - universal\n")
        (tmp_project / "pyproject.toml").write_text("[project]\nname = 'foo'")
        config = load_config(str(tmp_project))
        # Explicit packs should be used, not auto-detected
        assert config.packs == ["universal"]

    def test_custom_rules_dir(self, tmp_project):
        yml = tmp_project / "agentlint.yml"
        yml.write_text("custom_rules_dir: .agentlint/rules/\n")
        config = load_config(str(tmp_project))
        assert config.custom_rules_dir == ".agentlint/rules/"


class TestAgentLintConfig:
    def test_is_rule_enabled_default(self):
        config = AgentLintConfig(packs=["universal"])
        assert config.is_rule_enabled("no-secrets") is True

    def test_is_rule_disabled(self):
        config = AgentLintConfig(
            packs=["universal"],
            rules={"no-secrets": {"enabled": False}},
        )
        assert config.is_rule_enabled("no-secrets") is False

    def test_get_rule_config(self):
        config = AgentLintConfig(
            packs=["universal"],
            rules={"max-file-size": {"limit": 300}},
        )
        assert config.get_rule_config("max-file-size") == {"limit": 300}

    def test_get_rule_config_missing(self):
        config = AgentLintConfig(packs=["universal"])
        assert config.get_rule_config("nonexistent") == {}

    def test_effective_severity_standard(self):
        config = AgentLintConfig(severity="standard")
        from agentlint.models import Severity

        assert config.effective_severity(Severity.ERROR) == Severity.ERROR
        assert config.effective_severity(Severity.WARNING) == Severity.WARNING

    def test_effective_severity_strict(self):
        config = AgentLintConfig(severity="strict")
        from agentlint.models import Severity

        assert config.effective_severity(Severity.WARNING) == Severity.ERROR
        assert config.effective_severity(Severity.INFO) == Severity.WARNING

    def test_effective_severity_relaxed(self):
        config = AgentLintConfig(severity="relaxed")
        from agentlint.models import Severity

        assert config.effective_severity(Severity.WARNING) == Severity.INFO
        assert config.effective_severity(Severity.ERROR) == Severity.ERROR
```

**Step 6: Implement config**

```python
# src/agentlint/config.py
"""Configuration loading and parsing for AgentLint."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from agentlint.detector import detect_stack
from agentlint.models import Severity

CONFIG_FILENAMES = ["agentlint.yml", "agentlint.yaml", ".agentlint.yml"]


@dataclass
class AgentLintConfig:
    """Parsed AgentLint configuration."""

    severity: str = "standard"
    packs: list[str] = field(default_factory=lambda: ["universal"])
    rules: dict[str, dict] = field(default_factory=dict)
    custom_rules_dir: str | None = None

    def is_rule_enabled(self, rule_id: str) -> bool:
        rule_cfg = self.rules.get(rule_id, {})
        return rule_cfg.get("enabled", True)

    def get_rule_config(self, rule_id: str) -> dict:
        return self.rules.get(rule_id, {})

    def effective_severity(self, base: Severity) -> Severity:
        if self.severity == "strict":
            if base == Severity.WARNING:
                return Severity.ERROR
            if base == Severity.INFO:
                return Severity.WARNING
        elif self.severity == "relaxed":
            if base == Severity.WARNING:
                return Severity.INFO
        return base


def load_config(project_dir: str) -> AgentLintConfig:
    """Load config from agentlint.yml or auto-detect defaults."""
    root = Path(project_dir)

    # Try to find config file
    raw = {}
    for filename in CONFIG_FILENAMES:
        config_path = root / filename
        if config_path.exists():
            raw = yaml.safe_load(config_path.read_text()) or {}
            break

    # Determine packs
    stack_mode = raw.get("stack", "auto")
    explicit_packs = raw.get("packs")

    if explicit_packs:
        packs = explicit_packs
    elif stack_mode == "auto":
        packs = detect_stack(project_dir)
    else:
        packs = ["universal"]

    return AgentLintConfig(
        severity=raw.get("severity", "standard"),
        packs=packs,
        rules=raw.get("rules", {}),
        custom_rules_dir=raw.get("custom_rules_dir"),
    )
```

**Step 7: Run all config tests**

```bash
uv run pytest tests/test_config.py tests/test_detector.py -v
```

Expected: All PASS

**Step 8: Commit**

```bash
git add src/agentlint/config.py src/agentlint/detector.py tests/test_config.py tests/test_detector.py
git commit -m "feat: add config parser with YAML loading and stack auto-detection"
```

---

### Task 4: Reporter — Claude Code Output Formatting

**Files:**
- Create: `src/agentlint/reporter.py`
- Create: `tests/test_reporter.py`

**Step 1: Write failing tests**

```python
# tests/test_reporter.py
"""Tests for Claude Code output reporter."""
import json

from agentlint.models import Severity, Violation
from agentlint.reporter import Reporter


class TestReporter:
    def test_no_violations_returns_empty(self):
        reporter = Reporter(violations=[])
        output = reporter.format_hook_output()
        assert output is None

    def test_warnings_produce_system_message(self):
        violations = [
            Violation(
                rule_id="test-rule",
                message="Something wrong",
                severity=Severity.WARNING,
            )
        ]
        reporter = Reporter(violations=violations)
        output = reporter.format_hook_output()
        parsed = json.loads(output)
        assert "systemMessage" in parsed
        assert "test-rule" in parsed["systemMessage"]

    def test_error_violations_set_blocking(self):
        violations = [
            Violation(
                rule_id="no-secrets",
                message="API key found",
                severity=Severity.ERROR,
            )
        ]
        reporter = Reporter(violations=violations)
        assert reporter.has_blocking_violations() is True

    def test_warning_violations_not_blocking(self):
        violations = [
            Violation(
                rule_id="test-rule",
                message="Minor issue",
                severity=Severity.WARNING,
            )
        ]
        reporter = Reporter(violations=violations)
        assert reporter.has_blocking_violations() is False

    def test_exit_code_for_blocking(self):
        violations = [
            Violation(rule_id="x", message="bad", severity=Severity.ERROR)
        ]
        reporter = Reporter(violations=violations)
        assert reporter.exit_code() == 2

    def test_exit_code_for_non_blocking(self):
        violations = [
            Violation(rule_id="x", message="ok", severity=Severity.WARNING)
        ]
        reporter = Reporter(violations=violations)
        assert reporter.exit_code() == 0

    def test_format_session_report(self):
        violations = [
            Violation(rule_id="a", message="err", severity=Severity.ERROR),
            Violation(rule_id="b", message="warn", severity=Severity.WARNING),
            Violation(rule_id="c", message="info", severity=Severity.INFO),
        ]
        reporter = Reporter(violations=violations, rules_evaluated=50)
        report = reporter.format_session_report(files_changed=5)
        assert "Files changed: 5" in report
        assert "Rules evaluated: 50" in report
        assert "Blocked: 1" in report

    def test_format_hook_output_includes_suggestion(self):
        violations = [
            Violation(
                rule_id="test",
                message="Issue found",
                severity=Severity.WARNING,
                suggestion="Do this instead",
            )
        ]
        reporter = Reporter(violations=violations)
        output = reporter.format_hook_output()
        parsed = json.loads(output)
        assert "Do this instead" in parsed["systemMessage"]
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_reporter.py -v
```

Expected: FAIL

**Step 3: Implement reporter**

```python
# src/agentlint/reporter.py
"""Output formatting for Claude Code hook protocol."""
from __future__ import annotations

import json

from agentlint.models import Severity, Violation

SEVERITY_ICONS = {
    Severity.ERROR: "X",
    Severity.WARNING: "!",
    Severity.INFO: "i",
}


class Reporter:
    """Formats violations for Claude Code hook output."""

    def __init__(
        self,
        violations: list[Violation],
        rules_evaluated: int = 0,
    ):
        self.violations = violations
        self.rules_evaluated = rules_evaluated

    def has_blocking_violations(self) -> bool:
        return any(v.severity == Severity.ERROR for v in self.violations)

    def exit_code(self) -> int:
        return 2 if self.has_blocking_violations() else 0

    def format_hook_output(self) -> str | None:
        """Format violations as Claude Code hook JSON output."""
        if not self.violations:
            return None

        lines = ["", "AgentLint:"]

        errors = [v for v in self.violations if v.severity == Severity.ERROR]
        warnings = [v for v in self.violations if v.severity == Severity.WARNING]
        infos = [v for v in self.violations if v.severity == Severity.INFO]

        if errors:
            lines.append("  BLOCKED:")
            for v in errors:
                lines.append(f"    [{v.rule_id}] {v.message}")
                if v.suggestion:
                    lines.append(f"      -> {v.suggestion}")

        if warnings:
            lines.append("  WARNINGS:")
            for v in warnings:
                lines.append(f"    [{v.rule_id}] {v.message}")
                if v.suggestion:
                    lines.append(f"      -> {v.suggestion}")

        if infos:
            lines.append("  INFO:")
            for v in infos:
                lines.append(f"    [{v.rule_id}] {v.message}")
                if v.suggestion:
                    lines.append(f"      -> {v.suggestion}")

        return json.dumps({"systemMessage": "\n".join(lines)})

    def format_session_report(self, files_changed: int = 0) -> str:
        """Format a session summary report for the Stop event."""
        errors = [v for v in self.violations if v.severity == Severity.ERROR]
        warnings = [v for v in self.violations if v.severity == Severity.WARNING]
        infos = [v for v in self.violations if v.severity == Severity.INFO]

        lines = [
            "AgentLint Session Report",
            f"Files changed: {files_changed}  |  Rules evaluated: {self.rules_evaluated}",
            f"Passed: {self.rules_evaluated - len(self.violations)}  |  "
            f"Warnings: {len(warnings)}  |  Blocked: {len(errors)}",
        ]

        if errors:
            lines.append("")
            lines.append("Blocked actions:")
            for v in errors:
                lines.append(f"  [{v.rule_id}] {v.message}")

        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for v in warnings:
                lines.append(f"  [{v.rule_id}] {v.message}")

        return "\n".join(lines)
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_reporter.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/agentlint/reporter.py tests/test_reporter.py
git commit -m "feat: add reporter for Claude Code hook output formatting"
```

---

### Task 5: Engine — Rule Loading + Evaluation Orchestrator

**Files:**
- Create: `src/agentlint/engine.py`
- Create: `tests/test_engine.py`

**Step 1: Write failing tests**

```python
# tests/test_engine.py
"""Tests for the AgentLint engine."""
import pytest

from agentlint.config import AgentLintConfig
from agentlint.engine import Engine
from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation


class PassRule(Rule):
    id = "pass-rule"
    description = "Always passes"
    severity = Severity.INFO
    events = [HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE]
    pack = "test"

    def evaluate(self, context):
        return []


class FailRule(Rule):
    id = "fail-rule"
    description = "Always fails"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "test"

    def evaluate(self, context):
        return [Violation(rule_id=self.id, message="Failed", severity=self.severity)]


class WarnRule(Rule):
    id = "warn-rule"
    description = "Always warns"
    severity = Severity.WARNING
    events = [HookEvent.POST_TOOL_USE]
    pack = "test"

    def evaluate(self, context):
        return [Violation(rule_id=self.id, message="Warning", severity=self.severity)]


class TestEngine:
    def _make_context(self, event=HookEvent.PRE_TOOL_USE):
        return RuleContext(
            event=event,
            tool_name="Bash",
            tool_input={"command": "echo test"},
            project_dir="/tmp",
        )

    def test_evaluate_with_no_rules(self):
        config = AgentLintConfig(packs=["test"])
        engine = Engine(config=config, rules=[])
        result = engine.evaluate(self._make_context())
        assert result.violations == []
        assert result.rules_evaluated == 0

    def test_evaluate_matching_event(self):
        config = AgentLintConfig(packs=["test"])
        engine = Engine(config=config, rules=[FailRule()])
        result = engine.evaluate(self._make_context(HookEvent.PRE_TOOL_USE))
        assert len(result.violations) == 1

    def test_skips_non_matching_event(self):
        config = AgentLintConfig(packs=["test"])
        engine = Engine(config=config, rules=[FailRule()])
        result = engine.evaluate(self._make_context(HookEvent.POST_TOOL_USE))
        assert len(result.violations) == 0

    def test_skips_disabled_rules(self):
        config = AgentLintConfig(
            packs=["test"],
            rules={"fail-rule": {"enabled": False}},
        )
        engine = Engine(config=config, rules=[FailRule()])
        result = engine.evaluate(self._make_context())
        assert len(result.violations) == 0

    def test_skips_rules_from_inactive_packs(self):
        config = AgentLintConfig(packs=["universal"])  # 'test' pack not active
        engine = Engine(config=config, rules=[FailRule()])
        result = engine.evaluate(self._make_context())
        assert len(result.violations) == 0

    def test_multiple_rules(self):
        config = AgentLintConfig(packs=["test"])
        engine = Engine(config=config, rules=[PassRule(), FailRule()])
        result = engine.evaluate(self._make_context())
        assert len(result.violations) == 1
        assert result.rules_evaluated == 2

    def test_severity_override_strict(self):
        config = AgentLintConfig(severity="strict", packs=["test"])
        engine = Engine(config=config, rules=[WarnRule()])
        result = engine.evaluate(self._make_context(HookEvent.POST_TOOL_USE))
        # In strict mode, WARNING becomes ERROR
        assert result.violations[0].severity == Severity.ERROR

    def test_result_has_blocking_flag(self):
        config = AgentLintConfig(packs=["test"])
        engine = Engine(config=config, rules=[FailRule()])
        result = engine.evaluate(self._make_context())
        assert result.is_blocking is True

    def test_result_not_blocking_for_warnings(self):
        config = AgentLintConfig(packs=["test"])
        engine = Engine(config=config, rules=[WarnRule()])
        result = engine.evaluate(self._make_context(HookEvent.POST_TOOL_USE))
        assert result.is_blocking is False
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_engine.py -v
```

Expected: FAIL

**Step 3: Implement engine**

```python
# src/agentlint/engine.py
"""AgentLint evaluation engine."""
from __future__ import annotations

from dataclasses import dataclass, field

from agentlint.config import AgentLintConfig
from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation


@dataclass
class EvaluationResult:
    """Result of evaluating rules against a context."""

    violations: list[Violation] = field(default_factory=list)
    rules_evaluated: int = 0

    @property
    def is_blocking(self) -> bool:
        return any(v.severity == Severity.ERROR for v in self.violations)


class Engine:
    """Orchestrates rule loading and evaluation."""

    def __init__(self, config: AgentLintConfig, rules: list[Rule]):
        self.config = config
        self.rules = rules

    def evaluate(self, context: RuleContext) -> EvaluationResult:
        """Evaluate all applicable rules against the context."""
        result = EvaluationResult()

        for rule in self.rules:
            # Skip rules from inactive packs
            if rule.pack not in self.config.packs:
                continue

            # Skip disabled rules
            if not self.config.is_rule_enabled(rule.id):
                continue

            # Skip rules that don't match this event
            if not rule.matches_event(context.event):
                continue

            result.rules_evaluated += 1

            violations = rule.evaluate(context)

            # Apply severity overrides
            for v in violations:
                v.severity = self.config.effective_severity(v.severity)

            result.violations.extend(violations)

        return result
```

**Step 4: Run tests**

```bash
uv run pytest tests/test_engine.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/agentlint/engine.py tests/test_engine.py
git commit -m "feat: add evaluation engine with pack/event filtering and severity overrides"
```

---

### Task 6: Universal Rule Pack — First 5 Rules

**Files:**
- Create: `src/agentlint/packs/__init__.py`
- Create: `src/agentlint/packs/universal/__init__.py`
- Create: `src/agentlint/packs/universal/no_secrets.py`
- Create: `src/agentlint/packs/universal/no_env_commit.py`
- Create: `src/agentlint/packs/universal/no_force_push.py`
- Create: `src/agentlint/packs/universal/no_destructive_commands.py`
- Create: `src/agentlint/packs/universal/dependency_hygiene.py`
- Create: `tests/packs/__init__.py`
- Create: `tests/packs/test_universal_pre.py`

**Step 1: Write failing tests for PreToolUse rules**

```python
# tests/packs/test_universal_pre.py
"""Tests for universal pack PreToolUse rules."""
import pytest

from agentlint.models import HookEvent, RuleContext, Severity


def _ctx(tool_name: str, tool_input: dict) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
    )


class TestNoSecrets:
    @pytest.fixture
    def rule(self):
        from agentlint.packs.universal.no_secrets import NoSecrets
        return NoSecrets()

    def test_blocks_api_key_in_write(self, rule):
        ctx = _ctx("Write", {
            "file_path": "/tmp/config.py",
            "content": 'API_KEY = "sk_live_TESTKEY000000"',
        })
        violations = rule.evaluate(ctx)
        assert len(violations) >= 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_password_in_content(self, rule):
        ctx = _ctx("Write", {
            "file_path": "/tmp/settings.py",
            "content": 'password = "SuperSecret123!"',
        })
        violations = rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_allows_placeholder_values(self, rule):
        ctx = _ctx("Write", {
            "file_path": "/tmp/config.py",
            "content": 'API_KEY = os.environ["API_KEY"]',
        })
        violations = rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_test_values(self, rule):
        ctx = _ctx("Write", {
            "file_path": "/tmp/config.py",
            "content": 'API_KEY = "test_key"',
        })
        violations = rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_write_tools(self, rule):
        ctx = _ctx("Bash", {"command": "echo hello"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 0


class TestNoEnvCommit:
    @pytest.fixture
    def rule(self):
        from agentlint.packs.universal.no_env_commit import NoEnvCommit
        return NoEnvCommit()

    def test_blocks_writing_dot_env(self, rule):
        ctx = _ctx("Write", {"file_path": "/tmp/project/.env", "content": "KEY=val"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_env_local(self, rule):
        ctx = _ctx("Write", {"file_path": "/tmp/.env.local", "content": "KEY=val"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_env_example(self, rule):
        ctx = _ctx("Write", {"file_path": "/tmp/.env.example", "content": "KEY="})
        violations = rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_regular_files(self, rule):
        ctx = _ctx("Write", {"file_path": "/tmp/app.py", "content": "x = 1"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 0


class TestNoForcePush:
    @pytest.fixture
    def rule(self):
        from agentlint.packs.universal.no_force_push import NoForcePush
        return NoForcePush()

    def test_blocks_force_push_to_main(self, rule):
        ctx = _ctx("Bash", {"command": "git push --force origin main"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_force_push_to_master(self, rule):
        ctx = _ctx("Bash", {"command": "git push -f origin master"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_allows_regular_push(self, rule):
        ctx = _ctx("Bash", {"command": "git push origin feature-branch"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_force_push_to_feature(self, rule):
        ctx = _ctx("Bash", {"command": "git push --force origin feature-branch"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ignores_non_bash(self, rule):
        ctx = _ctx("Write", {"file_path": "/tmp/foo.py", "content": "git push --force"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 0


class TestNoDestructiveCommands:
    @pytest.fixture
    def rule(self):
        from agentlint.packs.universal.no_destructive_commands import NoDestructiveCommands
        return NoDestructiveCommands()

    def test_warns_rm_rf(self, rule):
        ctx = _ctx("Bash", {"command": "rm -rf /important"})
        violations = rule.evaluate(ctx)
        assert len(violations) >= 1
        assert violations[0].severity == Severity.WARNING

    def test_warns_drop_table(self, rule):
        ctx = _ctx("Bash", {"command": "psql -c 'DROP TABLE users'"})
        violations = rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_warns_git_reset_hard(self, rule):
        ctx = _ctx("Bash", {"command": "git reset --hard HEAD~3"})
        violations = rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_allows_safe_commands(self, rule):
        ctx = _ctx("Bash", {"command": "ls -la"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_rm_on_node_modules(self, rule):
        ctx = _ctx("Bash", {"command": "rm -rf node_modules"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 0


class TestDependencyHygiene:
    @pytest.fixture
    def rule(self):
        from agentlint.packs.universal.dependency_hygiene import DependencyHygiene
        return DependencyHygiene()

    def test_warns_pip_install(self, rule):
        ctx = _ctx("Bash", {"command": "pip install requests"})
        violations = rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_allows_poetry_add(self, rule):
        ctx = _ctx("Bash", {"command": "poetry add requests"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allows_uv_add(self, rule):
        ctx = _ctx("Bash", {"command": "uv add requests"})
        violations = rule.evaluate(ctx)
        assert len(violations) == 0
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/packs/test_universal_pre.py -v
```

Expected: FAIL

**Step 3: Implement the 5 PreToolUse rules**

Create `src/agentlint/packs/__init__.py` and `src/agentlint/packs/universal/__init__.py` as empty files, then implement each rule. Each rule follows the same pattern: subclass Rule, define class attributes, implement `evaluate()`.

Key implementation notes:
- `no_secrets.py`: Use regex patterns for API keys (stripe `sk_live_`, AWS `AKIA`, generic `password = "..."` with length > 8). Skip values that look like env var references, "test", "example", placeholders.
- `no_env_commit.py`: Check file_path ends with `.env`, `.env.local`, `.env.production` etc. Allow `.env.example`, `.env.template`.
- `no_force_push.py`: Regex for `git push.*(--force|-f).*(main|master)` in Bash commands only.
- `no_destructive_commands.py`: Regex for `rm -rf` (except node_modules, __pycache__, .cache, dist, build), `DROP TABLE`, `git reset --hard`, `git clean -fd`. Bash tool only.
- `dependency_hygiene.py`: Regex for `pip install` (not `pip install -e .` for local dev), `npm install <package>` (allow `npm ci`, `npm install` with no args). Bash tool only.

Pack `__init__.py` registers all rules:

```python
# src/agentlint/packs/universal/__init__.py
from agentlint.packs.universal.no_secrets import NoSecrets
from agentlint.packs.universal.no_env_commit import NoEnvCommit
from agentlint.packs.universal.no_force_push import NoForcePush
from agentlint.packs.universal.no_destructive_commands import NoDestructiveCommands
from agentlint.packs.universal.dependency_hygiene import DependencyHygiene

RULES = [
    NoSecrets(),
    NoEnvCommit(),
    NoForcePush(),
    NoDestructiveCommands(),
    DependencyHygiene(),
]
```

**Step 4: Run tests**

```bash
uv run pytest tests/packs/test_universal_pre.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/agentlint/packs/ tests/packs/
git commit -m "feat: add universal pack PreToolUse rules — secrets, env, force-push, destructive, deps"
```

---

### Task 7: Universal Rule Pack — Remaining 5 Rules

**Files:**
- Create: `src/agentlint/packs/universal/max_file_size.py`
- Create: `src/agentlint/packs/universal/no_debug_artifacts.py`
- Create: `src/agentlint/packs/universal/no_todo_left.py`
- Create: `src/agentlint/packs/universal/test_with_changes.py`
- Create: `src/agentlint/packs/universal/drift_detector.py`
- Create: `src/agentlint/utils/__init__.py`
- Create: `src/agentlint/utils/git.py`
- Create: `tests/packs/test_universal_post.py`
- Create: `tests/packs/test_universal_stop.py`

**Step 1: Write failing tests for PostToolUse rules**

```python
# tests/packs/test_universal_post.py
"""Tests for universal pack PostToolUse rules."""
from agentlint.models import HookEvent, RuleContext


def _post_ctx(file_path: str, content: str) -> RuleContext:
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name="Write",
        tool_input={"file_path": file_path},
        project_dir="/tmp/project",
        file_content=content,
    )


class TestMaxFileSize:
    def test_warns_large_file(self):
        from agentlint.packs.universal.max_file_size import MaxFileSize
        rule = MaxFileSize()
        content = "\n".join([f"line {i}" for i in range(600)])
        ctx = _post_ctx("/tmp/big.py", content)
        violations = rule.evaluate(ctx)
        assert len(violations) == 1

    def test_passes_small_file(self):
        from agentlint.packs.universal.max_file_size import MaxFileSize
        rule = MaxFileSize()
        ctx = _post_ctx("/tmp/small.py", "x = 1\ny = 2\n")
        violations = rule.evaluate(ctx)
        assert len(violations) == 0

    def test_custom_limit_from_config(self):
        from agentlint.packs.universal.max_file_size import MaxFileSize
        rule = MaxFileSize()
        content = "\n".join([f"line {i}" for i in range(250)])
        ctx = _post_ctx("/tmp/mid.py", content)
        ctx.config = {"max-file-size": {"limit": 200}}
        violations = rule.evaluate(ctx)
        assert len(violations) == 1


class TestDriftDetector:
    def test_warns_after_threshold_edits(self):
        from agentlint.packs.universal.drift_detector import DriftDetector
        rule = DriftDetector()
        state = {"files_edited": 0, "last_test_run": False}

        for i in range(11):
            ctx = _post_ctx(f"/tmp/file{i}.py", "content")
            ctx.session_state = state
            violations = rule.evaluate(ctx)

        assert len(violations) >= 1
        assert "test" in violations[0].message.lower()

    def test_resets_after_test_run(self):
        from agentlint.packs.universal.drift_detector import DriftDetector
        rule = DriftDetector()
        state = {"files_edited": 15, "last_test_run": False}

        # Simulate a test run
        ctx = RuleContext(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "pytest tests/"},
            project_dir="/tmp/project",
            session_state=state,
        )
        rule.evaluate(ctx)
        assert state["files_edited"] == 0
```

**Step 2: Write failing tests for Stop rules**

```python
# tests/packs/test_universal_stop.py
"""Tests for universal pack Stop rules."""
from agentlint.models import HookEvent, RuleContext


def _stop_ctx(project_dir: str = "/tmp/project") -> RuleContext:
    return RuleContext(
        event=HookEvent.STOP,
        tool_name="",
        tool_input={},
        project_dir=project_dir,
    )


class TestNoDebugArtifacts:
    def test_detects_console_log(self, tmp_path):
        from agentlint.packs.universal.no_debug_artifacts import NoDebugArtifacts
        rule = NoDebugArtifacts()
        src = tmp_path / "app.ts"
        src.write_text("console.log('debug');\nconst x = 1;")
        ctx = _stop_ctx(str(tmp_path))
        ctx.session_state = {"changed_files": [str(src)]}
        violations = rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_ignores_test_files(self, tmp_path):
        from agentlint.packs.universal.no_debug_artifacts import NoDebugArtifacts
        rule = NoDebugArtifacts()
        src = tmp_path / "test_app.py"
        src.write_text("print('test output')")
        ctx = _stop_ctx(str(tmp_path))
        ctx.session_state = {"changed_files": [str(src)]}
        violations = rule.evaluate(ctx)
        assert len(violations) == 0


class TestNoTodoLeft:
    def test_detects_todo_comments(self, tmp_path):
        from agentlint.packs.universal.no_todo_left import NoTodoLeft
        rule = NoTodoLeft()
        src = tmp_path / "app.py"
        src.write_text("# TODO: fix this later\nx = 1")
        ctx = _stop_ctx(str(tmp_path))
        ctx.session_state = {"changed_files": [str(src)]}
        violations = rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_detects_fixme(self, tmp_path):
        from agentlint.packs.universal.no_todo_left import NoTodoLeft
        rule = NoTodoLeft()
        src = tmp_path / "app.py"
        src.write_text("// FIXME: broken\nconst x = 1;")
        ctx = _stop_ctx(str(tmp_path))
        ctx.session_state = {"changed_files": [str(src)]}
        violations = rule.evaluate(ctx)
        assert len(violations) >= 1


class TestTestWithChanges:
    def test_warns_when_source_changed_without_tests(self):
        from agentlint.packs.universal.test_with_changes import TestWithChanges
        rule = TestWithChanges()
        ctx = _stop_ctx()
        ctx.session_state = {
            "changed_files": ["/tmp/project/src/app.py", "/tmp/project/src/utils.py"]
        }
        violations = rule.evaluate(ctx)
        assert len(violations) >= 1

    def test_passes_when_tests_also_changed(self):
        from agentlint.packs.universal.test_with_changes import TestWithChanges
        rule = TestWithChanges()
        ctx = _stop_ctx()
        ctx.session_state = {
            "changed_files": ["/tmp/project/src/app.py", "/tmp/project/tests/test_app.py"]
        }
        violations = rule.evaluate(ctx)
        assert len(violations) == 0
```

**Step 3: Implement all 5 rules + git utils**

Key implementation notes:
- `max_file_size.py`: Count lines in `file_content`. Default limit 500, override from `context.config.get("max-file-size", {}).get("limit", 500)`.
- `drift_detector.py`: Uses `session_state` dict — increments `files_edited` on each file write, checks if `pytest`/`vitest`/`jest` appears in Bash commands to reset counter.
- `no_debug_artifacts.py`: On Stop event, reads `session_state["changed_files"]`, scans for `console.log`, `print(`, `debugger`, `pdb.set_trace`. Skip test files.
- `no_todo_left.py`: On Stop event, scans changed files for `TODO`, `FIXME`, `HACK`, `XXX` patterns.
- `test_with_changes.py`: On Stop event, checks if any changed files are source files and whether any test files were also changed.
- `git.py`: Helper to get changed files via `git diff --name-only`.

Update `src/agentlint/packs/universal/__init__.py` to include all 10 rules in RULES list.

**Step 4: Run all tests**

```bash
uv run pytest tests/packs/ -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add src/agentlint/packs/universal/ src/agentlint/utils/ tests/packs/
git commit -m "feat: add universal PostToolUse + Stop rules — file size, drift, debug, todo, tests"
```

---

### Task 8: CLI Entry Point

**Files:**
- Create: `src/agentlint/cli.py`
- Create: `tests/test_cli.py`

**Step 1: Write failing tests**

```python
# tests/test_cli.py
"""Tests for the AgentLint CLI."""
import json

from click.testing import CliRunner

from agentlint.cli import main


class TestCheckCommand:
    def test_check_with_no_input(self):
        runner = CliRunner()
        result = runner.invoke(main, ["check", "--event", "PreToolUse"], input="{}")
        assert result.exit_code == 0

    def test_check_blocks_secrets(self, tmp_path):
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        input_json = json.dumps({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/config.py",
                "content": 'API_KEY = "sk_live_TESTKEY000000"',
            },
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
            input=input_json,
        )
        assert result.exit_code == 2

    def test_check_passes_clean_code(self, tmp_path):
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        input_json = json.dumps({
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/tmp/app.py",
                "content": "x = 1",
            },
        })
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["check", "--event", "PreToolUse", "--project-dir", str(tmp_path)],
            input=input_json,
        )
        assert result.exit_code == 0


class TestInitCommand:
    def test_init_creates_config(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--project-dir", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "agentlint.yml").exists()

    def test_init_detects_python(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'")
        runner = CliRunner()
        result = runner.invoke(main, ["init", "--project-dir", str(tmp_path)])
        config_content = (tmp_path / "agentlint.yml").read_text()
        assert "python" in config_content


class TestReportCommand:
    def test_report_outputs_summary(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--project-dir", str(tmp_path)],
            input="{}",
        )
        assert result.exit_code == 0
```

**Step 2: Implement CLI**

```python
# src/agentlint/cli.py
"""AgentLint CLI entry point."""
from __future__ import annotations

import json
import os
import sys

import click

from agentlint.config import load_config
from agentlint.detector import detect_stack
from agentlint.engine import Engine
from agentlint.models import HookEvent, RuleContext
from agentlint.packs import load_rules
from agentlint.reporter import Reporter


@click.group()
def main():
    """AgentLint - Real-time quality guardrails for AI coding agents."""


@main.command()
@click.option("--event", required=True, help="Hook event type (PreToolUse, PostToolUse, Stop)")
@click.option("--project-dir", default=None, help="Project directory")
def check(event: str, project_dir: str | None):
    """Evaluate rules against a tool call from stdin."""
    project_dir = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    # Parse event
    hook_event = HookEvent.from_string(event)

    # Read tool input from stdin
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError:
        raw = {}

    # Load config and rules
    config = load_config(project_dir)
    rules = load_rules(config.packs)

    # Build context
    context = RuleContext(
        event=hook_event,
        tool_name=raw.get("tool_name", ""),
        tool_input=raw.get("tool_input", {}),
        project_dir=project_dir,
    )

    # For PostToolUse on file operations, read the file content
    if hook_event == HookEvent.POST_TOOL_USE and context.file_path:
        try:
            with open(context.file_path) as f:
                context = RuleContext(
                    event=context.event,
                    tool_name=context.tool_name,
                    tool_input=context.tool_input,
                    project_dir=context.project_dir,
                    file_content=f.read(),
                    config=config.rules,
                    session_state=context.session_state,
                )
        except (FileNotFoundError, PermissionError):
            pass

    # Evaluate
    engine = Engine(config=config, rules=rules)
    result = engine.evaluate(context)

    # Report
    reporter = Reporter(violations=result.violations, rules_evaluated=result.rules_evaluated)
    output = reporter.format_hook_output()
    if output:
        click.echo(output)

    sys.exit(reporter.exit_code())


@main.command()
@click.option("--project-dir", default=None, help="Project directory")
def init(project_dir: str | None):
    """Initialize AgentLint config in the project."""
    project_dir = project_dir or os.getcwd()
    packs = detect_stack(project_dir)

    config_content = f"""# AgentLint Configuration
# Docs: https://github.com/maupr92/agentlint

stack: auto

severity: standard  # strict | standard | relaxed

packs:
{chr(10).join(f'  - {p}' for p in packs)}

rules: {{}}
  # Override individual rules:
  # no-secrets:
  #   severity: error
  # max-file-size:
  #   limit: 300

# custom_rules_dir: .agentlint/rules/
"""
    config_path = os.path.join(project_dir, "agentlint.yml")
    with open(config_path, "w") as f:
        f.write(config_content)

    click.echo(f"Created {config_path}")
    click.echo(f"Detected packs: {', '.join(packs)}")


@main.command()
@click.option("--project-dir", default=None, help="Project directory")
def report(project_dir: str | None):
    """Generate session summary report (for Stop event)."""
    project_dir = project_dir or os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())

    # Read stdin (Stop event input)
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        pass

    reporter = Reporter(violations=[], rules_evaluated=0)
    report_text = reporter.format_session_report(files_changed=0)
    output = json.dumps({"systemMessage": report_text, "continue": True})
    click.echo(output)
```

Also create `src/agentlint/packs/__init__.py` with a `load_rules()` function that imports rules from active packs:

```python
# src/agentlint/packs/__init__.py
"""Rule pack loader."""
from __future__ import annotations

from agentlint.models import Rule

PACK_MODULES = {
    "universal": "agentlint.packs.universal",
}


def load_rules(active_packs: list[str]) -> list[Rule]:
    """Load rules from all active packs."""
    import importlib

    rules: list[Rule] = []
    for pack_name in active_packs:
        module_path = PACK_MODULES.get(pack_name)
        if module_path:
            module = importlib.import_module(module_path)
            rules.extend(getattr(module, "RULES", []))
    return rules
```

**Step 3: Run tests**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: All PASS

**Step 4: Verify CLI works end-to-end**

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' | uv run agentlint check --event PreToolUse --project-dir /tmp
```

Expected: exit code 2, output contains "no-force-push"

**Step 5: Commit**

```bash
git add src/agentlint/cli.py src/agentlint/packs/__init__.py tests/test_cli.py
git commit -m "feat: add CLI with check, init, and report commands"
```

---

### Task 9: Claude Code Plugin

**Files:**
- Create: `plugin/plugin.json`
- Create: `plugin/hooks/pre-tool-use.sh`
- Create: `plugin/hooks/post-tool-use.sh`
- Create: `plugin/hooks/stop.sh`
- Create: `plugin/commands/lint-status.md`
- Create: `plugin/commands/lint-config.md`

**Step 1: Create plugin manifest**

```json
{
  "name": "agentlint",
  "version": "0.1.0",
  "description": "Real-time quality guardrails for AI coding agents",
  "author": "maupr92",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "agentlint check --event PreToolUse --project-dir \"$CLAUDE_PROJECT_DIR\"",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "agentlint check --event PostToolUse --project-dir \"$CLAUDE_PROJECT_DIR\"",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "agentlint report --project-dir \"$CLAUDE_PROJECT_DIR\"",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

**Step 2: Create hook wrappers**

```bash
#!/bin/bash
# plugin/hooks/pre-tool-use.sh
cat | agentlint check --event PreToolUse --project-dir "$CLAUDE_PROJECT_DIR"
exit $?
```

```bash
#!/bin/bash
# plugin/hooks/post-tool-use.sh
cat | agentlint check --event PostToolUse --project-dir "$CLAUDE_PROJECT_DIR"
exit $?
```

```bash
#!/bin/bash
# plugin/hooks/stop.sh
cat | agentlint report --project-dir "$CLAUDE_PROJECT_DIR"
exit $?
```

**Step 3: Create slash commands**

```markdown
# plugin/commands/lint-status.md
---
name: lint-status
description: Show AgentLint status — active rules, violations this session, severity counts
---

Run `agentlint status --project-dir "$CLAUDE_PROJECT_DIR"` and show the user:
1. Which rule packs are active
2. How many rules are running
3. Any violations found this session
4. Current severity mode
```

```markdown
# plugin/commands/lint-config.md
---
name: lint-config
description: Show or edit AgentLint configuration
---

Read the `agentlint.yml` file in the project root and display:
1. Current severity mode
2. Active packs
3. Rule overrides
4. If user wants to change, edit the agentlint.yml file
```

**Step 4: Make hook scripts executable**

```bash
chmod +x plugin/hooks/*.sh
```

**Step 5: Commit**

```bash
git add plugin/
git commit -m "feat: add Claude Code plugin with hooks, commands"
```

---

### Task 10: Integration Test — End-to-End Validation

**Files:**
- Create: `tests/test_integration.py`
- Create: `tests/fixtures/tool_inputs/`

**Step 1: Write integration tests**

```python
# tests/test_integration.py
"""End-to-end integration tests for AgentLint."""
import json
import subprocess
import sys

import pytest


class TestEndToEnd:
    def _run_agentlint(self, args: list[str], stdin_data: dict | None = None, project_dir: str = "/tmp"):
        cmd = [sys.executable, "-m", "agentlint.cli"] + args + ["--project-dir", project_dir]
        input_data = json.dumps(stdin_data) if stdin_data else "{}"
        result = subprocess.run(
            cmd, input=input_data, capture_output=True, text=True, timeout=10
        )
        return result

    def test_blocks_secrets_end_to_end(self, tmp_path):
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "/tmp/config.py",
                    "content": 'SECRET = "sk_live_TESTKEY000000"',
                },
            },
            project_dir=str(tmp_path),
        )
        assert result.returncode == 2
        output = json.loads(result.stdout)
        assert "no-secrets" in output["systemMessage"]

    def test_allows_clean_code_end_to_end(self, tmp_path):
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Write",
                "tool_input": {
                    "file_path": "/tmp/app.py",
                    "content": "def add(a: int, b: int) -> int:\n    return a + b\n",
                },
            },
            project_dir=str(tmp_path),
        )
        assert result.returncode == 0

    def test_init_and_check_flow(self, tmp_path):
        # Create a Python project
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'")

        # Run init
        init_result = self._run_agentlint(["init"], project_dir=str(tmp_path))
        assert init_result.returncode == 0
        assert (tmp_path / "agentlint.yml").exists()

        # Verify config detected python
        config_content = (tmp_path / "agentlint.yml").read_text()
        assert "python" in config_content

        # Run check with the generated config
        check_result = self._run_agentlint(
            ["check", "--event", "PreToolUse"],
            stdin_data={
                "tool_name": "Bash",
                "tool_input": {"command": "pip install requests"},
            },
            project_dir=str(tmp_path),
        )
        # Should warn about pip install (dependency-hygiene rule)
        assert check_result.returncode == 0  # warning, not error
        output = json.loads(check_result.stdout)
        assert "dependency-hygiene" in output["systemMessage"]
```

**Step 2: Run integration tests**

```bash
uv run pytest tests/test_integration.py -v
```

Expected: All PASS

**Step 3: Run full test suite**

```bash
uv run pytest -v --tb=short
```

Expected: All tests pass

**Step 4: Commit**

```bash
git add tests/test_integration.py tests/fixtures/
git commit -m "feat: add end-to-end integration tests"
```

---

### Task 11: Final Polish — README + gitignore + Example Config

**Files:**
- Create: `.gitignore`
- Create: `agentlint.yml.example`

**Step 1: Create .gitignore**

Standard Python gitignore: `__pycache__/`, `*.pyc`, `.venv/`, `dist/`, `*.egg-info/`, `.pytest_cache/`

**Step 2: Create example config**

```yaml
# agentlint.yml.example
# Copy to your project root as agentlint.yml

stack: auto          # auto-detect from project files

severity: standard   # strict | standard | relaxed
#   strict:   all warnings become errors (blocks agent)
#   standard: errors block, warnings shown (default)
#   relaxed:  only critical errors block

packs:
  - universal        # always recommended
  # - python         # auto-detected from pyproject.toml
  # - react          # auto-detected from package.json

rules: {}
  # Override individual rules:
  # no-secrets:
  #   severity: error
  # max-file-size:
  #   limit: 300
  # drift-detector:
  #   threshold: 5
  # no-debug-artifacts:
  #   enabled: false

# Custom rules directory:
# custom_rules_dir: .agentlint/rules/
```

**Step 3: Run full test suite one final time**

```bash
uv run pytest -v --cov=agentlint --cov-report=term-missing
```

Expected: All tests pass, reasonable coverage

**Step 4: Commit**

```bash
git add .gitignore agentlint.yml.example
git commit -m "chore: add gitignore and example config"
```

---

## Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Project scaffolding (uv, pyproject.toml) | Install verification |
| 2 | Core models (Rule, Violation, RuleContext) | 15+ unit tests |
| 3 | Config parser + stack auto-detection | 14+ unit tests |
| 4 | Reporter (Claude Code output formatting) | 8+ unit tests |
| 5 | Engine (rule loading + evaluation) | 9+ unit tests |
| 6 | Universal PreToolUse rules (5 rules) | 20+ unit tests |
| 7 | Universal PostToolUse + Stop rules (5 rules) | 10+ unit tests |
| 8 | CLI (check, init, report commands) | 6+ unit tests |
| 9 | Claude Code plugin (hooks, commands) | Manual verification |
| 10 | Integration tests | 3+ E2E tests |
| 11 | Final polish (gitignore, example config) | Full suite run |

**Total: ~85+ tests across 11 tasks**
