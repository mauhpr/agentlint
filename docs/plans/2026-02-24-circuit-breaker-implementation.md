# Circuit Breaker Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a circuit breaker that automatically degrades blocking rules to advisory after repeated fires, preventing buggy rules from locking agents in a loop.

**Architecture:** New `circuit_breaker.py` module with state machine (ACTIVE -> DEGRADED -> PASSIVE -> OPEN). Injected into `Engine.evaluate()` after rule evaluation, before reporter. State persisted in existing session state dict. ON by default, security-critical rules exempt.

**Tech Stack:** Python 3.11+, dataclasses, enum, time (stdlib only — no new dependencies)

---

### Task 1: Circuit Breaker Core Module — State and Config

**Files:**
- Create: `src/agentlint/circuit_breaker.py`
- Test: `tests/test_circuit_breaker.py`

**Step 1: Write the failing tests for state enum and config dataclass**

In `tests/test_circuit_breaker.py`:

```python
"""Tests for AgentLint circuit breaker."""
from __future__ import annotations

import time

import pytest

from agentlint.circuit_breaker import (
    CircuitBreakerConfig,
    CircuitBreakerState,
    apply_circuit_breaker,
)
from agentlint.models import Severity, Violation


def _v(rule_id: str = "test-rule", severity: Severity = Severity.ERROR) -> Violation:
    return Violation(rule_id=rule_id, message="test", severity=severity)


class TestCircuitBreakerState:
    def test_states_exist(self) -> None:
        assert CircuitBreakerState.ACTIVE.value == "active"
        assert CircuitBreakerState.DEGRADED.value == "degraded"
        assert CircuitBreakerState.PASSIVE.value == "passive"
        assert CircuitBreakerState.OPEN.value == "open"


class TestCircuitBreakerConfig:
    def test_defaults(self) -> None:
        cfg = CircuitBreakerConfig()
        assert cfg.enabled is True
        assert cfg.degraded_after == 3
        assert cfg.passive_after == 6
        assert cfg.open_after == 10
        assert cfg.reset_after_clean == 5
        assert cfg.reset_after_minutes == 30

    def test_disabled(self) -> None:
        cfg = CircuitBreakerConfig(enabled=False)
        assert cfg.enabled is False
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_circuit_breaker.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'agentlint.circuit_breaker'"

**Step 3: Write minimal implementation — state and config**

In `src/agentlint/circuit_breaker.py`:

```python
"""Circuit breaker to prevent buggy rules from blocking agents repeatedly.

When a rule fires too many times in a session (likely a false positive),
the circuit breaker degrades it: ERROR -> WARNING -> INFO -> suppressed.
This prevents a single buggy rule from locking the agent in a loop.

ON by default. Security-critical rules (no-secrets, no-env-commit) are exempt.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from agentlint.models import Severity, Violation

# Rules that should never be auto-degraded (security-critical).
_CB_NEVER_DEGRADE = {"no-secrets", "no-env-commit"}


class CircuitBreakerState(Enum):
    """Circuit breaker states for a single rule."""
    ACTIVE = "active"       # Normal — rule blocks as designed
    DEGRADED = "degraded"   # ERROR -> WARNING (visible, not blocking)
    PASSIVE = "passive"     # WARNING -> INFO (minimal noise)
    OPEN = "open"           # Suppressed entirely (only in session report)


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    enabled: bool = True
    degraded_after: int = 3        # ERROR -> WARNING after N fires
    passive_after: int = 6         # WARNING -> INFO after N fires
    open_after: int = 10           # Suppressed after N fires
    reset_after_clean: int = 5     # Reset after N clean evaluations
    reset_after_minutes: int = 30  # Reset after N minutes without fire
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_circuit_breaker.py -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add src/agentlint/circuit_breaker.py tests/test_circuit_breaker.py
git commit -m "feat: add circuit breaker state and config"
```

---

### Task 2: Circuit Breaker Core — apply_circuit_breaker Function

**Files:**
- Modify: `src/agentlint/circuit_breaker.py`
- Test: `tests/test_circuit_breaker.py`

**Step 1: Write failing tests for apply_circuit_breaker**

Append to `tests/test_circuit_breaker.py`:

```python
class TestApplyCircuitBreaker:
    def test_first_fire_stays_active(self) -> None:
        """First violation should pass through unchanged."""
        session_state: dict = {}
        violations = [_v()]
        result = apply_circuit_breaker(violations, session_state, {})
        assert len(result) == 1
        assert result[0].severity == Severity.ERROR

    def test_degrades_after_threshold(self) -> None:
        """After degraded_after fires, ERROR should become WARNING."""
        session_state: dict = {}
        cfg = CircuitBreakerConfig(degraded_after=3)

        # Simulate 2 previous fires
        for _ in range(2):
            apply_circuit_breaker([_v()], session_state, {})

        # 3rd fire should trigger degradation
        result = apply_circuit_breaker([_v()], session_state, {})
        assert len(result) == 1
        assert result[0].severity == Severity.WARNING

    def test_passive_after_threshold(self) -> None:
        """After passive_after fires, should become INFO."""
        session_state: dict = {}
        cfg_dict: dict = {}

        for _ in range(5):
            apply_circuit_breaker([_v()], session_state, cfg_dict)

        # 6th fire -> PASSIVE
        result = apply_circuit_breaker([_v()], session_state, cfg_dict)
        assert len(result) == 1
        assert result[0].severity == Severity.INFO

    def test_open_after_threshold(self) -> None:
        """After open_after fires, violations should be suppressed."""
        session_state: dict = {}
        cfg_dict: dict = {}

        for _ in range(9):
            apply_circuit_breaker([_v()], session_state, cfg_dict)

        # 10th fire -> OPEN (suppressed)
        result = apply_circuit_breaker([_v()], session_state, cfg_dict)
        assert len(result) == 0

    def test_no_violations_increments_clean_count(self) -> None:
        """Empty violations should increment the clean counter."""
        session_state: dict = {}
        cfg_dict: dict = {}

        # Fire 3 times to reach DEGRADED
        for _ in range(3):
            apply_circuit_breaker([_v()], session_state, cfg_dict)

        # 5 clean evaluations should reset
        for _ in range(5):
            apply_circuit_breaker([], session_state, cfg_dict)

        # Next fire should be back to ACTIVE (ERROR)
        result = apply_circuit_breaker([_v()], session_state, cfg_dict)
        assert len(result) == 1
        assert result[0].severity == Severity.ERROR

    def test_disabled_passes_through(self) -> None:
        """When disabled, violations pass through unchanged."""
        session_state: dict = {}
        cfg_dict = {"circuit_breaker": {"enabled": False}}

        for _ in range(20):
            result = apply_circuit_breaker([_v()], session_state, cfg_dict)
        assert len(result) == 1
        assert result[0].severity == Severity.ERROR

    def test_security_rules_never_degrade(self) -> None:
        """no-secrets and no-env-commit should never be degraded."""
        session_state: dict = {}

        for _ in range(20):
            result = apply_circuit_breaker(
                [_v(rule_id="no-secrets")], session_state, {}
            )
        assert len(result) == 1
        assert result[0].severity == Severity.ERROR

    def test_multiple_rules_tracked_independently(self) -> None:
        """Each rule has its own fire counter."""
        session_state: dict = {}

        # Fire rule-a 3 times (reaches DEGRADED)
        for _ in range(3):
            apply_circuit_breaker([_v(rule_id="rule-a")], session_state, {})

        # rule-b should still be ACTIVE
        result = apply_circuit_breaker([_v(rule_id="rule-b")], session_state, {})
        assert result[0].severity == Severity.ERROR

    def test_per_rule_config_override(self) -> None:
        """Per-rule circuit_breaker config overrides globals."""
        session_state: dict = {}
        cfg_dict = {
            "test-rule": {"circuit_breaker": {"degraded_after": 5}},
        }

        # 3 fires should still be ACTIVE with custom threshold of 5
        for _ in range(3):
            result = apply_circuit_breaker([_v()], session_state, cfg_dict)
        assert result[0].severity == Severity.ERROR

        # 5th fire should degrade
        apply_circuit_breaker([_v()], session_state, cfg_dict)
        result = apply_circuit_breaker([_v()], session_state, cfg_dict)
        assert result[0].severity == Severity.WARNING

    def test_warning_violations_not_affected(self) -> None:
        """Circuit breaker only tracks ERROR violations for degradation."""
        session_state: dict = {}

        for _ in range(20):
            result = apply_circuit_breaker(
                [_v(severity=Severity.WARNING)], session_state, {}
            )
        # WARNING violations are never degraded by CB
        assert result[0].severity == Severity.WARNING
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_circuit_breaker.py::TestApplyCircuitBreaker -v`
Expected: FAIL with "cannot import name 'apply_circuit_breaker'"

**Step 3: Implement apply_circuit_breaker**

Add to `src/agentlint/circuit_breaker.py`:

```python
def _get_cb_config(rule_id: str, rules_config: dict) -> CircuitBreakerConfig:
    """Build CB config from global defaults + per-rule overrides."""
    # Check global circuit_breaker config
    global_cb = rules_config.get("circuit_breaker", {})
    # Check per-rule circuit_breaker config
    rule_cb = rules_config.get(rule_id, {}).get("circuit_breaker", {})

    merged = {**global_cb, **rule_cb}

    return CircuitBreakerConfig(
        enabled=merged.get("enabled", True),
        degraded_after=merged.get("degraded_after", 3),
        passive_after=merged.get("passive_after", 6),
        open_after=merged.get("open_after", 10),
        reset_after_clean=merged.get("reset_after_clean", 5),
        reset_after_minutes=merged.get("reset_after_minutes", 30),
    )


def _get_rule_state(cb_data: dict, config: CircuitBreakerConfig) -> CircuitBreakerState:
    """Determine the current state based on fire count."""
    count = cb_data.get("fire_count", 0)
    if count >= config.open_after:
        return CircuitBreakerState.OPEN
    if count >= config.passive_after:
        return CircuitBreakerState.PASSIVE
    if count >= config.degraded_after:
        return CircuitBreakerState.DEGRADED
    return CircuitBreakerState.ACTIVE


def _downgrade_severity(severity: Severity, state: CircuitBreakerState) -> Severity | None:
    """Downgrade severity based on CB state. Returns None if suppressed."""
    if state == CircuitBreakerState.ACTIVE:
        return severity
    if state == CircuitBreakerState.DEGRADED:
        if severity == Severity.ERROR:
            return Severity.WARNING
        return severity
    if state == CircuitBreakerState.PASSIVE:
        if severity in (Severity.ERROR, Severity.WARNING):
            return Severity.INFO
        return severity
    # OPEN — suppress
    return None


def apply_circuit_breaker(
    violations: list[Violation],
    session_state: dict,
    rules_config: dict,
) -> list[Violation]:
    """Apply circuit breaker degradation to violations.

    Tracks per-rule fire counts in session_state and downgrades severity
    when a rule fires too many times (likely a false positive).

    Args:
        violations: Violations from engine evaluation.
        session_state: Mutable session dict (persisted across hook calls).
        rules_config: The config.rules dict for per-rule CB overrides.

    Returns:
        Filtered/degraded list of violations.
    """
    cb_store = session_state.setdefault("circuit_breaker", {})

    # Track which rules fired this evaluation
    fired_rule_ids = set()
    result = []

    for v in violations:
        # Only track ERROR violations for circuit breaker (WARNING/INFO pass through)
        if v.severity != Severity.ERROR:
            result.append(v)
            continue

        # Security-critical rules are never degraded
        if v.rule_id in _CB_NEVER_DEGRADE:
            result.append(v)
            continue

        # Get CB config for this rule
        config = _get_cb_config(v.rule_id, rules_config)
        if not config.enabled:
            result.append(v)
            continue

        # Get/create per-rule CB data
        rule_cb = cb_store.setdefault(v.rule_id, {
            "fire_count": 0,
            "clean_count": 0,
            "first_fire_ts": None,
            "last_fire_ts": None,
            "state": CircuitBreakerState.ACTIVE.value,
            "transitions": [],
        })

        # Increment fire count and reset clean count
        rule_cb["fire_count"] = rule_cb.get("fire_count", 0) + 1
        rule_cb["clean_count"] = 0
        now = time.time()
        if rule_cb.get("first_fire_ts") is None:
            rule_cb["first_fire_ts"] = now
        rule_cb["last_fire_ts"] = now

        fired_rule_ids.add(v.rule_id)

        # Determine state and record transitions
        old_state = rule_cb.get("state", "active")
        state = _get_rule_state(rule_cb, config)
        rule_cb["state"] = state.value

        if state.value != old_state:
            rule_cb.setdefault("transitions", []).append({
                "from": old_state,
                "to": state.value,
                "at_count": rule_cb["fire_count"],
                "ts": now,
            })

        # Apply degradation
        new_severity = _downgrade_severity(v.severity, state)
        if new_severity is None:
            continue  # OPEN — suppressed
        v.severity = new_severity
        result.append(v)

    # Track clean evaluations for rules that DIDN'T fire
    for rule_id, rule_cb in cb_store.items():
        if rule_id not in fired_rule_ids:
            config = _get_cb_config(rule_id, rules_config)
            rule_cb["clean_count"] = rule_cb.get("clean_count", 0) + 1

            # Reset if enough clean evaluations
            if rule_cb["clean_count"] >= config.reset_after_clean:
                rule_cb["fire_count"] = 0
                rule_cb["clean_count"] = 0
                rule_cb["state"] = CircuitBreakerState.ACTIVE.value
                continue

            # Reset if time window expired
            last_fire = rule_cb.get("last_fire_ts")
            if last_fire and (time.time() - last_fire) > config.reset_after_minutes * 60:
                rule_cb["fire_count"] = 0
                rule_cb["clean_count"] = 0
                rule_cb["state"] = CircuitBreakerState.ACTIVE.value

    return result
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_circuit_breaker.py -v`
Expected: PASS (all tests)

**Step 5: Commit**

```bash
git add src/agentlint/circuit_breaker.py tests/test_circuit_breaker.py
git commit -m "feat: implement apply_circuit_breaker with state machine"
```

---

### Task 3: Integrate Circuit Breaker into Engine

**Files:**
- Modify: `src/agentlint/engine.py:31-56`
- Modify: `tests/test_engine.py`

**Step 1: Write failing test for engine CB integration**

Add to `tests/test_engine.py`:

```python
class TestEngineCircuitBreaker:
    def test_engine_applies_circuit_breaker(self) -> None:
        """After threshold fires, engine should degrade ERROR to WARNING."""
        config = AgentLintConfig(packs=["test"])
        context = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": "rm -rf /"},
            project_dir="/tmp",
            session_state={},
        )

        engine = Engine(config=config, rules=[FailRule()])

        # Fire 3 times — 3rd should be degraded
        for _ in range(2):
            result = engine.evaluate(context)
            assert result.violations[0].severity == Severity.ERROR

        result = engine.evaluate(context)
        assert result.violations[0].severity == Severity.WARNING
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_engine.py::TestEngineCircuitBreaker -v`
Expected: FAIL (violations still ERROR on 3rd fire)

**Step 3: Modify engine.py to call apply_circuit_breaker**

In `src/agentlint/engine.py`, add import and call after line 54:

```python
from agentlint.circuit_breaker import apply_circuit_breaker
```

After `result.violations.extend(violations)` (line 54), add:

```python
        # Apply circuit breaker degradation
        result.violations = apply_circuit_breaker(
            result.violations, context.session_state, context.config,
        )
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_engine.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/agentlint/engine.py tests/test_engine.py
git commit -m "feat: integrate circuit breaker into engine evaluation"
```

---

### Task 4: Session Report — Circuit Breaker Activity Section

**Files:**
- Modify: `src/agentlint/reporter.py:92-116`
- Test: `tests/test_reporter.py`

**Step 1: Write failing test**

Add to `tests/test_reporter.py`:

```python
class TestSessionReportCircuitBreaker:
    def test_report_includes_cb_activity(self) -> None:
        """Session report should show degraded rules."""
        violations = [_make_violation(severity=Severity.WARNING)]
        reporter = Reporter(violations=violations, rules_evaluated=5)
        cb_state = {
            "no-destructive-commands": {
                "fire_count": 4,
                "state": "degraded",
            },
        }
        report = reporter.format_session_report(files_changed=1, cb_state=cb_state)
        assert "Circuit Breaker" in report
        assert "no-destructive-commands" in report
        assert "degraded" in report

    def test_report_no_cb_section_when_empty(self) -> None:
        """No CB section when no rules were degraded."""
        reporter = Reporter(violations=[], rules_evaluated=5)
        report = reporter.format_session_report(files_changed=0, cb_state={})
        assert "Circuit Breaker" not in report

    def test_report_no_cb_section_when_all_active(self) -> None:
        """No CB section when all rules are still ACTIVE."""
        reporter = Reporter(violations=[], rules_evaluated=5)
        cb_state = {
            "some-rule": {"fire_count": 1, "state": "active"},
        }
        report = reporter.format_session_report(files_changed=0, cb_state=cb_state)
        assert "Circuit Breaker" not in report
```

**Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_reporter.py::TestSessionReportCircuitBreaker -v`
Expected: FAIL (TypeError: format_session_report() got unexpected keyword argument 'cb_state')

**Step 3: Modify reporter.py**

Update `format_session_report` in `src/agentlint/reporter.py`:

```python
    def format_session_report(self, files_changed: int = 0, cb_state: dict | None = None) -> str:
        """Format a session summary report for the Stop event."""
        errors = [v for v in self.violations if v.severity == Severity.ERROR]
        warnings = [v for v in self.violations if v.severity == Severity.WARNING]

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

        # Circuit breaker activity (only show non-active rules)
        if cb_state:
            degraded = {
                rid: data for rid, data in cb_state.items()
                if data.get("state", "active") != "active"
            }
            if degraded:
                lines.append("")
                lines.append("Circuit Breaker:")
                for rid, data in sorted(degraded.items()):
                    state = data.get("state", "unknown")
                    count = data.get("fire_count", 0)
                    lines.append(f"  [{rid}] {state} (fired {count}x)")

        return "\n".join(lines)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_reporter.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/agentlint/reporter.py tests/test_reporter.py
git commit -m "feat: add circuit breaker activity to session report"
```

---

### Task 5: Wire CB State into CLI Report Command

**Files:**
- Modify: `src/agentlint/cli.py:236-241`
- Test: `tests/test_cli.py`

**Step 1: Write failing test**

Add to `tests/test_cli.py`:

```python
class TestReportCircuitBreaker:
    def test_report_shows_cb_activity(self, tmp_path, monkeypatch) -> None:
        """Report should include circuit breaker data from session."""
        from agentlint.session import save_session

        monkeypatch.setenv("AGENTLINT_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv("CLAUDE_SESSION_ID", "test-cb-report")

        save_session({
            "circuit_breaker": {
                "no-destructive-commands": {
                    "fire_count": 5,
                    "state": "degraded",
                }
            }
        })

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["report", "--project-dir", str(tmp_path)],
            input="{}",
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert "Circuit Breaker" in parsed["systemMessage"]
        assert "no-destructive-commands" in parsed["systemMessage"]
```

**Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_cli.py::TestReportCircuitBreaker -v`
Expected: FAIL ("Circuit Breaker" not in output)

**Step 3: Modify cli.py report command**

In `src/agentlint/cli.py`, update the report command around line 239-240:

```python
    reporter = Reporter(violations=result.violations, rules_evaluated=result.rules_evaluated)
    cb_state = session_state.get("circuit_breaker", {})
    report_text = reporter.format_session_report(files_changed=len(changed_files), cb_state=cb_state)
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/agentlint/cli.py tests/test_cli.py
git commit -m "feat: wire circuit breaker state into session report"
```

---

### Task 6: Config Integration — Global and Per-Rule CB Settings

**Files:**
- Modify: `src/agentlint/config.py`
- Test: `tests/test_config.py`

**Step 1: Write failing tests**

Add to `tests/test_config.py`:

```python
class TestCircuitBreakerConfig:
    def test_default_cb_config_in_loaded_config(self, tmp_path) -> None:
        """Config should include circuit_breaker settings."""
        (tmp_path / "agentlint.yml").write_text(
            "packs:\n  - universal\ncircuit_breaker:\n  degraded_after: 5\n"
        )
        config = load_config(str(tmp_path))
        assert config.circuit_breaker.get("degraded_after") == 5

    def test_cb_config_absent_uses_empty_dict(self, tmp_path) -> None:
        """Missing circuit_breaker in yml should give empty dict."""
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")
        config = load_config(str(tmp_path))
        assert config.circuit_breaker == {}
```

**Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_config.py::TestCircuitBreakerConfig -v`
Expected: FAIL (AttributeError: 'AgentLintConfig' has no attribute 'circuit_breaker')

**Step 3: Add circuit_breaker field to AgentLintConfig**

In `src/agentlint/config.py`:

Add field to `AgentLintConfig`:
```python
    circuit_breaker: dict = field(default_factory=dict)
```

In `load_config()`, add to the return:
```python
        circuit_breaker=raw.get("circuit_breaker", {}),
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: ALL PASS

**Step 5: Pass CB config through to rules_config in cli.py**

In `src/agentlint/cli.py`, where `RuleContext` is built (around line 65-76), ensure `circuit_breaker` global config is accessible. Modify the config dict passed to context to include it:

After `config = load_config(project_dir)` (line 55), add:
```python
    rules_config = config.rules
    if config.circuit_breaker:
        rules_config = {**rules_config, "circuit_breaker": config.circuit_breaker}
```

Then use `rules_config` instead of `config.rules` in the RuleContext.

**Step 6: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add src/agentlint/config.py src/agentlint/cli.py tests/test_config.py
git commit -m "feat: add circuit_breaker field to config and wire to engine"
```

---

### Task 7: Integration Test — Full E2E Circuit Breaker

**Files:**
- Modify: `tests/test_integration.py`

**Step 1: Write E2E test**

Add to `tests/test_integration.py`:

```python
    def test_circuit_breaker_degrades_after_threshold(self, tmp_path):
        """After 3 identical blocks, rule should degrade to warning (not block)."""
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")

        # Fire the same blocking rule 3 times
        for i in range(3):
            result = self._run_agentlint(
                ["check", "--event", "PreToolUse"],
                stdin_data={
                    "tool_name": "Bash",
                    "tool_input": {"command": "git push --force origin main"},
                },
                project_dir=str(tmp_path),
            )
            assert result.returncode == 0
            output = json.loads(result.stdout)

            if i < 2:
                # First 2 fires should block (deny protocol)
                assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
            else:
                # 3rd fire should be degraded to warning (systemMessage)
                assert "systemMessage" in output
                assert "hookSpecificOutput" not in output

    def test_circuit_breaker_never_degrades_secrets(self, tmp_path):
        """no-secrets should never be degraded by circuit breaker."""
        (tmp_path / "agentlint.yml").write_text("packs:\n  - universal\n")

        for _ in range(5):
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
            assert result.returncode == 0
            output = json.loads(result.stdout)
            # Should ALWAYS block — never degraded
            assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
```

**Step 2: Run to verify they pass (integration)**

Run: `uv run pytest tests/test_integration.py -v`
Expected: ALL PASS

Note: These are subprocess tests so they run the full CLI. The session state must persist across calls for the same `tmp_path`. Set `CLAUDE_SESSION_ID` env var in `_run_agentlint` to ensure consistent session key. May need to update the helper:

```python
    def _run_agentlint(self, args: list[str], stdin_data: dict | None = None, project_dir: str = "/tmp"):
        cmd = [sys.executable, "-m", "agentlint.cli"] + args + ["--project-dir", project_dir]
        input_data = json.dumps(stdin_data) if stdin_data else "{}"
        env = {**os.environ, "CLAUDE_SESSION_ID": f"test-{project_dir}"}
        result = subprocess.run(
            cmd, input=input_data, capture_output=True, text=True, timeout=10, env=env,
        )
        return result
```

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add E2E integration tests for circuit breaker"
```

---

### Task 8: Version Bump, Changelog, Final Test Run

**Files:**
- Modify: `pyproject.toml` — version "0.5.3" -> "0.6.0"
- Modify: `plugin/.claude-plugin/plugin.json` — version "0.5.3" -> "0.6.0"
- Modify: `CHANGELOG.md` — add v0.6.0 entry

**Step 1: Update pyproject.toml**

```
version = "0.6.0"
```

**Step 2: Update plugin.json**

```
"version": "0.6.0"
```

**Step 3: Update CHANGELOG.md**

Add at top (after `# Changelog`):

```markdown
## 0.6.0 (2026-02-24) — "Progressive Trust"

Automatic circuit breaker prevents buggy rules from locking agents in a loop.

### New: Circuit Breaker (ON by default)

- **Automatic degradation** — When a blocking rule (ERROR) fires 3+ times in a session, it degrades to WARNING (advisory). Fires 6+ → INFO. Fires 10+ → suppressed. Prevents false positive loops.
- **Security-critical rules exempt** — `no-secrets` and `no-env-commit` never degrade (too important). All other rules opt-out via config.
- **Auto-reset** — 5 consecutive clean evaluations or 30 minutes without fire resets the circuit breaker.
- **Session report transparency** — Stop report includes "Circuit Breaker" section showing which rules were degraded and fire counts.
- **Fully configurable** — Global thresholds in `circuit_breaker:` config block. Per-rule overrides via `rules: <rule-id>: circuit_breaker:`.

### Tests

- ~780 tests, 96% coverage
```

**Step 4: Run full test suite**

Run: `uv run pytest -v --cov=agentlint --cov-report=term-missing`
Expected: ALL PASS, 96%+ coverage

**Step 5: Commit**

```bash
git add pyproject.toml plugin/.claude-plugin/plugin.json CHANGELOG.md uv.lock
git commit -m "chore: bump to v0.6.0, update changelog"
```

---

## Verification Checklist

After all tasks are complete:

```bash
# 1. Full test suite passes
uv run pytest -v --cov=agentlint --cov-report=term-missing

# 2. Circuit breaker fires correctly
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force origin main"}}' | \
  CLAUDE_SESSION_ID=test uv run python -m agentlint check --event PreToolUse --project-dir /tmp

# 3. Run it 3 times — 3rd should degrade
# (repeat above command 3 times, observe JSON output change)

# 4. no-secrets never degrades
echo '{"tool_name":"Write","tool_input":{"file_path":"x.py","content":"sk_live_KEY"}}' | \
  CLAUDE_SESSION_ID=test2 uv run python -m agentlint check --event PreToolUse --project-dir /tmp
# (repeat 5 times — all should use deny protocol)
```
