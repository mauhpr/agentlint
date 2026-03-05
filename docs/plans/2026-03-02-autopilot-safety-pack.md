# Autopilot Safety Pack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a new `autopilot` opt-in pack with 6 rules that protect agents running with `--dangerously-skip-permissions` from catastrophic actions against production systems (databases, cloud accounts, infrastructure).

**Architecture:** New `packs/autopilot/` directory mirroring the `security` pack structure — opt-in (not auto-detected), registered in `PACK_MODULES`, and activated via `packs: [autopilot]` in `agentlint.yml`. Three PreToolUse blocking rules, one PreToolUse rate-limit rule, one PostToolUse journal rule, and the journal also emits a Stop summary. All rules follow the exact pattern of existing security rules: import from `agentlint.models`, implement `evaluate(context) -> list[Violation]`.

**Tech Stack:** Python 3.11+, pytest, uv (run tests with `uv run pytest`), existing `agentlint.models.{Rule,RuleContext,Violation,Severity,HookEvent}`

---

## Task 1: Scaffold the `autopilot` pack

**Files:**
- Create: `src/agentlint/packs/autopilot/__init__.py`
- Modify: `src/agentlint/packs/__init__.py` (add `"autopilot"` to `PACK_MODULES`)

**Step 1: Write the failing test**

Create `tests/packs/test_autopilot_pack_loads.py`:

```python
"""Test that the autopilot pack scaffolding loads correctly."""
from agentlint.packs import PACK_MODULES, load_rules


def test_autopilot_registered_in_pack_modules():
    assert "autopilot" in PACK_MODULES


def test_autopilot_loads_without_error():
    rules = load_rules(["autopilot"])
    assert isinstance(rules, list)
    # Will grow as rules are added — starts at 0
    assert len(rules) == 0
```

**Step 2: Run test to verify it fails**

```bash
cd /Users/maupr92/Projects/agentlint
uv run pytest tests/packs/test_autopilot_pack_loads.py -v
```
Expected: FAIL — `"autopilot" not in PACK_MODULES`

**Step 3: Create the pack `__init__.py`**

`src/agentlint/packs/autopilot/__init__.py`:
```python
"""Autopilot safety rule pack — opt-in rules for agents running autonomously."""

RULES = []
```

**Step 4: Register the pack**

In `src/agentlint/packs/__init__.py`, add to `PACK_MODULES` dict:
```python
"autopilot": "agentlint.packs.autopilot",
```

**Step 5: Run test to verify it passes**

```bash
uv run pytest tests/packs/test_autopilot_pack_loads.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git add src/agentlint/packs/autopilot/__init__.py src/agentlint/packs/__init__.py tests/packs/test_autopilot_pack_loads.py
git commit -m "feat: scaffold autopilot safety pack"
```

---

## Task 2: `production-guard` rule

Detects when a Bash command targets a production database, gcloud project, or AWS account and blocks/warns. Production indicators: connection strings with `prod`/`production`/`live` in DB name or host, `--project` flags pointing to prod-named gcloud projects, AWS `--profile prod*`, `psql`/`mysql` against prod hosts.

**Files:**
- Create: `src/agentlint/packs/autopilot/production_guard.py`
- Create: `tests/packs/test_autopilot_pre.py`

**Step 1: Write the failing tests**

`tests/packs/test_autopilot_pre.py`:
```python
"""Tests for autopilot pack PreToolUse rules."""
from __future__ import annotations

import pytest

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.production_guard import ProductionGuard


def _ctx(command: str, config: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": command},
        project_dir="/tmp/project",
        config=config or {},
    )


class TestProductionGuard:
    rule = ProductionGuard()

    # --- Detection ---

    def test_blocks_psql_prod_connection_string(self):
        ctx = _ctx("psql postgresql://user:pass@prod-db.example.com/myapp")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_psql_production_database_name(self):
        ctx = _ctx("psql -h localhost -d production -U admin")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_gcloud_prod_project(self):
        ctx = _ctx("gcloud --project=my-production-project deploy")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_gcloud_project_flag_prod(self):
        ctx = _ctx("gcloud compute instances list --project prod-env-123")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_aws_prod_profile(self):
        ctx = _ctx("aws s3 ls --profile production")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_aws_prod_account_env(self):
        ctx = _ctx("AWS_PROFILE=prod aws ec2 describe-instances")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_mysql_prod_host(self):
        ctx = _ctx("mysql -h prod-mysql.internal -u root -p mydb")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_connection_string_with_live(self):
        ctx = _ctx("psql postgresql://user:pass@live-db.example.com/app")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Allowlist ---

    def test_allowed_project_passes(self):
        ctx = _ctx(
            "gcloud --project=my-production-project deploy",
            config={"production-guard": {"allowed_projects": ["my-production-project"]}},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_allowed_host_passes(self):
        ctx = _ctx(
            "psql -h prod-db.example.com -d myapp",
            config={"production-guard": {"allowed_hosts": ["prod-db.example.com"]}},
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    # --- Non-production pass through ---

    def test_dev_database_passes(self):
        ctx = _ctx("psql -h localhost -d myapp_dev -U admin")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_staging_database_passes(self):
        ctx = _ctx("psql -h staging-db.internal -d myapp_staging -U user")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_gcloud_dev_project_passes(self):
        ctx = _ctx("gcloud --project=my-dev-project compute instances list")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_non_bash_tool_ignored(self):
        from agentlint.models import RuleContext
        ctx = RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Write",
            tool_input={"file_path": "prod.py", "content": "x=1"},
            project_dir="/tmp/project",
        )
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/packs/test_autopilot_pre.py::TestProductionGuard -v
```
Expected: FAIL — `ModuleNotFoundError: production_guard`

**Step 3: Implement `production_guard.py`**

`src/agentlint/packs/autopilot/production_guard.py`:
```python
"""Rule: block Bash commands targeting production environments."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Patterns that indicate a production environment target.
# Each tuple: (compiled_regex, human-readable label).
_PROD_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # PostgreSQL/MySQL connection strings with prod/production/live in host.
    (re.compile(
        r"\bpsql\b.*(?:prod(?:uction)?|live)[-.]",
        re.IGNORECASE,
    ), "psql → production host"),
    (re.compile(
        r"\bpsql\b.*postgresql://[^@]+@[^/]*(?:prod(?:uction)?|live)[^/]*/",
        re.IGNORECASE,
    ), "psql → production connection string"),
    # psql -d production (database name is prod/production/live)
    (re.compile(
        r"\bpsql\b.*-d\s+(?:prod(?:uction)?|live)\b",
        re.IGNORECASE,
    ), "psql → production database name"),
    # mysql with prod host
    (re.compile(
        r"\bmysql\b.*-h\s+\S*(?:prod(?:uction)?|live)\S*",
        re.IGNORECASE,
    ), "mysql → production host"),
    # gcloud --project=<prod-named-project>
    (re.compile(
        r"\bgcloud\b.*--project[=\s]+\S*(?:prod(?:uction)?|live)\S*",
        re.IGNORECASE,
    ), "gcloud → production project"),
    # aws --profile prod*
    (re.compile(
        r"\baws\b.*--profile\s+(?:prod(?:uction)?|live)\S*",
        re.IGNORECASE,
    ), "aws → production profile"),
    # AWS_PROFILE=prod* environment variable
    (re.compile(
        r"\bAWS_PROFILE\s*=\s*(?:prod(?:uction)?|live)\S*",
        re.IGNORECASE,
    ), "AWS_PROFILE → production"),
]

# Extract project/host identifiers for allowlist checking.
_PROJECT_RE = re.compile(r"--project[=\s]+(\S+)", re.IGNORECASE)
_HOST_RE = re.compile(r"(?:-h\s+(\S+)|@([^/:]+))", re.IGNORECASE)


def _extract_project(command: str) -> str | None:
    m = _PROJECT_RE.search(command)
    return m.group(1).strip("'\"") if m else None


def _extract_host(command: str) -> str | None:
    m = _HOST_RE.search(command)
    if m:
        return (m.group(1) or m.group(2) or "").strip("'\"") or None
    return None


class ProductionGuard(Rule):
    """Block Bash commands that target production databases, cloud projects, or accounts."""

    id = "production-guard"
    description = "Blocks commands targeting production environments (DB, gcloud, AWS)"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        rule_config = context.config.get(self.id, {})
        allowed_projects: list[str] = [p.lower() for p in rule_config.get("allowed_projects", [])]
        allowed_hosts: list[str] = [h.lower() for h in rule_config.get("allowed_hosts", [])]

        # Check allowlists before pattern matching.
        project = _extract_project(command)
        if project and project.lower() in allowed_projects:
            return []

        host = _extract_host(command)
        if host and host.lower() in allowed_hosts:
            return []

        for pattern, label in _PROD_PATTERNS:
            if pattern.search(command):
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Production environment detected: {label}",
                        severity=self.severity,
                        suggestion=(
                            "Add this project/host to production-guard.allowed_projects or "
                            "allowed_hosts in agentlint.yml if this is intentional."
                        ),
                    )
                ]

        return []
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/packs/test_autopilot_pre.py::TestProductionGuard -v
```
Expected: All PASS

**Step 5: Add to pack `__init__.py`**

`src/agentlint/packs/autopilot/__init__.py`:
```python
"""Autopilot safety rule pack — opt-in rules for agents running autonomously."""
from agentlint.packs.autopilot.production_guard import ProductionGuard

RULES = [
    ProductionGuard(),
]
```

Update the pack loads test:
```python
def test_autopilot_loads_without_error():
    rules = load_rules(["autopilot"])
    assert len(rules) == 1  # ProductionGuard
```

**Step 6: Commit**

```bash
git add src/agentlint/packs/autopilot/ tests/packs/test_autopilot_pre.py tests/packs/test_autopilot_pack_loads.py
git commit -m "feat(autopilot): add production-guard rule"
```

---

## Task 3: `destructive-confirmation-gate` rule

Blocks the highest-risk irreversible operations unless the current session_state contains an explicit `"confirmed_destructive_ops"` acknowledgment key. Operations covered: `DROP DATABASE`, `DROP TABLE`, `terraform destroy`, `kubectl delete namespace`, `rm -rf /` (root/home already caught by `no-destructive-commands` as WARNING — this rule upgrades to ERROR block for confirmed catastrophic ops).

**Files:**
- Create: `src/agentlint/packs/autopilot/destructive_confirmation_gate.py`
- Modify: `tests/packs/test_autopilot_pre.py` (add `TestDestructiveConfirmationGate` class)

**Step 1: Add failing tests to `test_autopilot_pre.py`**

```python
from agentlint.packs.autopilot.destructive_confirmation_gate import DestructiveConfirmationGate


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
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/packs/test_autopilot_pre.py::TestDestructiveConfirmationGate -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement `destructive_confirmation_gate.py`**

```python
"""Rule: block catastrophic irreversible operations without explicit session confirmation."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Catastrophic operations: each entry is (compiled_regex, label, confirmation_key).
# confirmation_key is what must appear in session_state["confirmed_destructive_ops"].
_CATASTROPHIC_OPS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"\bDROP\s+DATABASE\b", re.IGNORECASE), "DROP DATABASE", "DROP DATABASE"),
    (re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE), "DROP TABLE", "DROP TABLE"),
    (re.compile(r"\bterraform\s+destroy\b", re.IGNORECASE), "terraform destroy", "terraform destroy"),
    (re.compile(r"\bkubectl\s+delete\s+namespace\b", re.IGNORECASE), "kubectl delete namespace", "kubectl delete namespace"),
    (re.compile(r"\bgcloud\s+projects?\s+delete\b", re.IGNORECASE), "gcloud project delete", "gcloud projects delete"),
    (re.compile(r"\bheroku\s+apps?\s+destroy\b", re.IGNORECASE), "heroku app destroy", "heroku apps destroy"),
]


class DestructiveConfirmationGate(Rule):
    """Block catastrophic irreversible ops unless session_state has explicit confirmation."""

    id = "destructive-confirmation-gate"
    description = "Blocks DROP DATABASE, terraform destroy, kubectl delete namespace without confirmation"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        # Confirmed ops in session state (set by user or a prior confirmation step)
        confirmed: list[str] = context.session_state.get("confirmed_destructive_ops", [])
        confirmed_lower = [c.lower() for c in confirmed]

        for pattern, label, key in _CATASTROPHIC_OPS:
            if pattern.search(command):
                if key.lower() in confirmed_lower:
                    continue
                return [
                    Violation(
                        rule_id=self.id,
                        message=f"Catastrophic operation requires explicit confirmation: {label}",
                        severity=self.severity,
                        suggestion=(
                            f"Set session_state['confirmed_destructive_ops'] = ['{key}'] "
                            f"before running this command, or add it to destructive-confirmation-gate.bypass_ops in agentlint.yml."
                        ),
                    )
                ]

        return []
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/packs/test_autopilot_pre.py::TestDestructiveConfirmationGate -v
```
Expected: All PASS

**Step 5: Add to `__init__.py`**

```python
from agentlint.packs.autopilot.destructive_confirmation_gate import DestructiveConfirmationGate

RULES = [
    ProductionGuard(),
    DestructiveConfirmationGate(),
]
```

Update the loads test count to `2`.

**Step 6: Commit**

```bash
git add src/agentlint/packs/autopilot/ tests/packs/test_autopilot_pre.py tests/packs/test_autopilot_pack_loads.py
git commit -m "feat(autopilot): add destructive-confirmation-gate rule"
```

---

## Task 4: `dry-run-required` rule

Requires `--dry-run`, `--check`, or `--plan` flags for infrastructure tools before allowing apply/deploy commands. Covered tools: `terraform apply` (requires `plan` first or `--dry-run`), `ansible-playbook` (requires `--check`), `kubectl apply` (requires `--dry-run=client`), `helm upgrade/install` (requires `--dry-run`).

**Files:**
- Create: `src/agentlint/packs/autopilot/dry_run_required.py`
- Modify: `tests/packs/test_autopilot_pre.py`

**Step 1: Add failing tests**

```python
from agentlint.packs.autopilot.dry_run_required import DryRunRequired


class TestDryRunRequired:
    rule = DryRunRequired()

    # --- Blocking apply without dry-run ---

    def test_blocks_terraform_apply_without_plan(self):
        ctx = _ctx("terraform apply")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.ERROR

    def test_blocks_terraform_apply_auto_approve(self):
        ctx = _ctx("terraform apply -auto-approve")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_ansible_without_check(self):
        ctx = _ctx("ansible-playbook site.yml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_kubectl_apply_without_dry_run(self):
        ctx = _ctx("kubectl apply -f deployment.yaml")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    def test_blocks_helm_upgrade_without_dry_run(self):
        ctx = _ctx("helm upgrade myapp ./chart")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1

    # --- Safe (has dry-run flag) ---

    def test_terraform_plan_passes(self):
        ctx = _ctx("terraform plan")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_ansible_check_mode_passes(self):
        ctx = _ctx("ansible-playbook site.yml --check")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_kubectl_apply_dry_run_passes(self):
        ctx = _ctx("kubectl apply -f deployment.yaml --dry-run=client")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_helm_upgrade_dry_run_passes(self):
        ctx = _ctx("helm upgrade myapp ./chart --dry-run")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0

    def test_kubectl_get_passes(self):
        ctx = _ctx("kubectl get pods")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/packs/test_autopilot_pre.py::TestDryRunRequired -v
```

**Step 3: Implement `dry_run_required.py`**

```python
"""Rule: require --dry-run/--check/plan flags for infrastructure apply commands."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

# Each entry: (apply_pattern, safe_pattern, label)
# apply_pattern matches the dangerous form; safe_pattern matches the safe (dry-run) form.
_INFRA_RULES: list[tuple[re.Pattern[str], re.Pattern[str], str]] = [
    (
        re.compile(r"\bterraform\s+apply\b", re.IGNORECASE),
        re.compile(r"\bterraform\s+plan\b|\b--dry-run\b", re.IGNORECASE),
        "terraform apply",
    ),
    (
        re.compile(r"\bansible-playbook\b", re.IGNORECASE),
        re.compile(r"\b--check\b", re.IGNORECASE),
        "ansible-playbook",
    ),
    (
        re.compile(r"\bkubectl\s+apply\b", re.IGNORECASE),
        re.compile(r"\b--dry-run\b", re.IGNORECASE),
        "kubectl apply",
    ),
    (
        re.compile(r"\bhelm\s+(?:upgrade|install)\b", re.IGNORECASE),
        re.compile(r"\b--dry-run\b", re.IGNORECASE),
        "helm upgrade/install",
    ),
    (
        re.compile(r"\bpulumi\s+up\b", re.IGNORECASE),
        re.compile(r"\b--dry-run\b|\bpulumi\s+preview\b", re.IGNORECASE),
        "pulumi up",
    ),
]


class DryRunRequired(Rule):
    """Require --dry-run/--check flags for infrastructure apply commands."""

    id = "dry-run-required"
    description = "Requires --dry-run/--check for terraform, kubectl, ansible, helm before apply"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        rule_config = context.config.get(self.id, {})
        bypass_tools: list[str] = rule_config.get("bypass_tools", [])

        violations: list[Violation] = []
        for apply_re, safe_re, label in _INFRA_RULES:
            if label in bypass_tools:
                continue
            if apply_re.search(command) and not safe_re.search(command):
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"Infrastructure apply without preview: {label}",
                        severity=self.severity,
                        suggestion=f"Run the dry-run/preview form first (e.g. terraform plan, kubectl apply --dry-run=client). Add to dry-run-required.bypass_tools in agentlint.yml to allow.",
                    )
                )
        return violations
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/packs/test_autopilot_pre.py::TestDryRunRequired -v
```

**Step 5: Add to `__init__.py`** (update count to 3 in loads test)

**Step 6: Commit**

```bash
git commit -am "feat(autopilot): add dry-run-required rule"
```

---

## Task 5: `bash-rate-limiter` rule

Tracks destructive Bash commands in session_state. If more than N destructive ops are executed within M seconds, blocks further execution (circuit-break the runaway loop). Destructive ops: `rm -rf`, `DROP TABLE/DATABASE`, `kubectl delete`, `terraform destroy`, `gcloud delete`. Configurable via `max_destructive_ops` (default: 5) and `window_seconds` (default: 300).

**Files:**
- Create: `src/agentlint/packs/autopilot/bash_rate_limiter.py`
- Modify: `tests/packs/test_autopilot_pre.py`

**Step 1: Add failing tests**

```python
import time
from agentlint.packs.autopilot.bash_rate_limiter import BashRateLimiter


class TestBashRateLimiter:
    rule = BashRateLimiter()

    def _ctx_with_state(self, command: str, state: dict | None = None, config: dict | None = None) -> RuleContext:
        return RuleContext(
            event=HookEvent.PRE_TOOL_USE,
            tool_name="Bash",
            tool_input={"command": command},
            project_dir="/tmp/project",
            config=config or {},
            session_state=state or {},
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
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/packs/test_autopilot_pre.py::TestBashRateLimiter -v
```

**Step 3: Implement `bash_rate_limiter.py`**

```python
"""Rule: circuit-break runaway destructive Bash command loops."""
from __future__ import annotations

import re
import time

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

_DESTRUCTIVE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+-[^\s]*r[^\s]*f|\brm\s+-[^\s]*f[^\s]*r", re.IGNORECASE),
    re.compile(r"\bDROP\s+(?:TABLE|DATABASE)\b", re.IGNORECASE),
    re.compile(r"\bkubectl\s+delete\b", re.IGNORECASE),
    re.compile(r"\bterraform\s+destroy\b", re.IGNORECASE),
    re.compile(r"\bgcloud\b.*\bdelete\b", re.IGNORECASE),
    re.compile(r"\baws\b.*\bdelete\b", re.IGNORECASE),
    re.compile(r"\bheroku\b.*\bdestroy\b", re.IGNORECASE),
]

_DEFAULT_MAX = 5
_DEFAULT_WINDOW = 300  # seconds


def _is_destructive(command: str) -> bool:
    return any(p.search(command) for p in _DESTRUCTIVE_PATTERNS)


class BashRateLimiter(Rule):
    """Block further execution after too many destructive commands in a time window."""

    id = "bash-rate-limiter"
    description = "Circuit-breaks after N destructive commands within a time window"
    severity = Severity.ERROR
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        if not _is_destructive(command):
            return []

        rule_config = context.config.get(self.id, {})
        max_ops = rule_config.get("max_destructive_ops", _DEFAULT_MAX)
        window_secs = rule_config.get("window_seconds", _DEFAULT_WINDOW)

        rl = context.session_state.setdefault("rate_limiter", {
            "destructive_count": 0,
            "window_start": time.time(),
        })

        now = time.time()
        # Reset window if expired
        if now - rl.get("window_start", now) >= window_secs:
            rl["destructive_count"] = 0
            rl["window_start"] = now

        # Check limit BEFORE incrementing (current command would be the (count+1)th)
        if rl.get("destructive_count", 0) >= max_ops:
            return [
                Violation(
                    rule_id=self.id,
                    message=(
                        f"Rate limit exceeded: {rl['destructive_count']} destructive commands "
                        f"in {window_secs}s window (max={max_ops})"
                    ),
                    severity=self.severity,
                    suggestion="The agent has executed too many destructive operations. Review session state and reset manually if intentional.",
                )
            ]

        # Increment after passing the check
        rl["destructive_count"] = rl.get("destructive_count", 0) + 1
        return []
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/packs/test_autopilot_pre.py::TestBashRateLimiter -v
```

**Step 5: Add to `__init__.py`** (update count to 4 in loads test)

**Step 6: Commit**

```bash
git commit -am "feat(autopilot): add bash-rate-limiter rule"
```

---

## Task 6: `cross-account-guard` rule

Warns when the agent switches between different cloud accounts, gcloud projects, or AWS profiles within the same session. Tracks "known accounts" in session_state. On first use, registers the account. On subsequent uses with a different account, emits a WARNING (advisory, not blocking — the agent may legitimately need to cross accounts).

**Files:**
- Create: `src/agentlint/packs/autopilot/cross_account_guard.py`
- Modify: `tests/packs/test_autopilot_pre.py`

**Step 1: Add failing tests**

```python
from agentlint.packs.autopilot.cross_account_guard import CrossAccountGuard


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

    def test_no_project_flag_ignored(self):
        ctx = self._ctx_with_state("gcloud compute instances list")
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 0
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/packs/test_autopilot_pre.py::TestCrossAccountGuard -v
```

**Step 3: Implement `cross_account_guard.py`**

```python
"""Rule: warn when the agent switches between cloud accounts/projects within a session."""
from __future__ import annotations

import re

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_BASH_TOOLS = {"Bash"}

_GCLOUD_PROJECT_RE = re.compile(r"--project[=\s]+(\S+)", re.IGNORECASE)
_AWS_PROFILE_RE = re.compile(r"(?:--profile\s+(\S+)|AWS_PROFILE\s*=\s*(\S+))", re.IGNORECASE)


def _extract_gcloud_project(command: str) -> str | None:
    m = _GCLOUD_PROJECT_RE.search(command)
    return m.group(1).strip("'\"").lower() if m else None


def _extract_aws_profile(command: str) -> str | None:
    m = _AWS_PROFILE_RE.search(command)
    if m:
        return (m.group(1) or m.group(2) or "").strip("'\"").lower() or None
    return None


class CrossAccountGuard(Rule):
    """Warn when the agent switches between different cloud accounts/projects in a session."""

    id = "cross-account-guard"
    description = "Warns on cloud account/project switches within the same session"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _BASH_TOOLS:
            return []

        command: str = context.command or ""
        if not command:
            return []

        ca = context.session_state.setdefault("cross_account", {
            "seen_gcloud_projects": [],
            "seen_aws_profiles": [],
        })

        violations: list[Violation] = []

        project = _extract_gcloud_project(command)
        if project:
            seen = ca.setdefault("seen_gcloud_projects", [])
            if seen and project not in seen:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"GCloud project switch detected: {seen[-1]} → {project}",
                        severity=self.severity,
                        suggestion="Verify this project switch is intentional. Previous project: " + seen[-1],
                    )
                )
            if project not in seen:
                seen.append(project)

        profile = _extract_aws_profile(command)
        if profile:
            seen = ca.setdefault("seen_aws_profiles", [])
            if seen and profile not in seen:
                violations.append(
                    Violation(
                        rule_id=self.id,
                        message=f"AWS profile switch detected: {seen[-1]} → {profile}",
                        severity=self.severity,
                        suggestion="Verify this profile switch is intentional. Previous profile: " + seen[-1],
                    )
                )
            if profile not in seen:
                seen.append(profile)

        return violations
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/packs/test_autopilot_pre.py::TestCrossAccountGuard -v
```

**Step 5: Add to `__init__.py`** (update count to 5 in loads test)

**Step 6: Commit**

```bash
git commit -am "feat(autopilot): add cross-account-guard rule"
```

---

## Task 7: `operation-journal` rule (PostToolUse + Stop)

Records every Bash command execution to an in-memory audit log in `session_state["operation_journal"]`. At `Stop`, emits the full journal as an INFO summary. This gives complete replay capability for debugging what an autonomous agent did.

**Files:**
- Create: `src/agentlint/packs/autopilot/operation_journal.py`
- Create: `tests/packs/test_autopilot_post.py`

**Step 1: Write failing tests**

`tests/packs/test_autopilot_post.py`:
```python
"""Tests for autopilot pack PostToolUse and Stop rules."""
from __future__ import annotations

import time

import pytest

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs.autopilot.operation_journal import OperationJournal


def _ctx_post(tool_name: str, tool_input: dict, state: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name=tool_name,
        tool_input=tool_input,
        project_dir="/tmp/project",
        config={},
        session_state=state if state is not None else {},
    )


def _ctx_stop(state: dict | None = None) -> RuleContext:
    return RuleContext(
        event=HookEvent.STOP,
        tool_name="",
        tool_input={},
        project_dir="/tmp/project",
        config={},
        session_state=state if state is not None else {},
    )


class TestOperationJournal:
    rule = OperationJournal()

    def test_records_bash_command_to_journal(self):
        state = {}
        ctx = _ctx_post("Bash", {"command": "ls -la"}, state=state)
        self.rule.evaluate(ctx)
        assert "operation_journal" in state
        assert len(state["operation_journal"]) == 1
        entry = state["operation_journal"][0]
        assert entry["tool"] == "Bash"
        assert entry["command"] == "ls -la"
        assert "ts" in entry

    def test_records_multiple_commands(self):
        state = {}
        for cmd in ["ls", "pwd", "whoami"]:
            ctx = _ctx_post("Bash", {"command": cmd}, state=state)
            self.rule.evaluate(ctx)
        assert len(state["operation_journal"]) == 3

    def test_records_write_tool(self):
        state = {}
        ctx = _ctx_post("Write", {"file_path": "foo.py", "content": "x=1"}, state=state)
        self.rule.evaluate(ctx)
        assert len(state["operation_journal"]) == 1
        assert state["operation_journal"][0]["tool"] == "Write"

    def test_post_returns_no_violations(self):
        state = {}
        ctx = _ctx_post("Bash", {"command": "ls"}, state=state)
        violations = self.rule.evaluate(ctx)
        assert violations == []

    def test_stop_emits_journal_summary(self):
        state = {
            "operation_journal": [
                {"ts": time.time(), "tool": "Bash", "command": "ls -la"},
                {"ts": time.time(), "tool": "Write", "file_path": "app.py"},
            ]
        }
        ctx = _ctx_stop(state=state)
        violations = self.rule.evaluate(ctx)
        assert len(violations) == 1
        assert violations[0].severity == Severity.INFO
        assert "2 operations" in violations[0].message

    def test_stop_with_empty_journal_no_violation(self):
        ctx = _ctx_stop(state={})
        violations = self.rule.evaluate(ctx)
        assert violations == []
```

**Step 2: Run to verify failure**

```bash
uv run pytest tests/packs/test_autopilot_post.py -v
```

**Step 3: Implement `operation_journal.py`**

```python
"""Rule: record all tool operations to a session audit log."""
from __future__ import annotations

import time

from agentlint.models import HookEvent, Rule, RuleContext, Severity, Violation

_TRACKED_TOOLS = {"Bash", "Write", "Edit", "MultiEdit"}


class OperationJournal(Rule):
    """Record every tool operation to session_state for audit/replay."""

    id = "operation-journal"
    description = "Records all tool operations to an audit log, emits summary at Stop"
    severity = Severity.INFO
    events = [HookEvent.POST_TOOL_USE, HookEvent.STOP]
    pack = "autopilot"

    def evaluate(self, context: RuleContext) -> list[Violation]:
        if context.event == HookEvent.POST_TOOL_USE:
            return self._record(context)
        if context.event == HookEvent.STOP:
            return self._summarize(context)
        return []

    def _record(self, context: RuleContext) -> list[Violation]:
        if context.tool_name not in _TRACKED_TOOLS:
            return []

        journal: list[dict] = context.session_state.setdefault("operation_journal", [])
        entry: dict = {"ts": time.time(), "tool": context.tool_name}

        if context.tool_name == "Bash":
            entry["command"] = context.tool_input.get("command", "")
        else:
            entry["file_path"] = context.tool_input.get("file_path", "")

        journal.append(entry)
        return []

    def _summarize(self, context: RuleContext) -> list[Violation]:
        journal: list[dict] = context.session_state.get("operation_journal", [])
        if not journal:
            return []

        total = len(journal)
        bash_count = sum(1 for e in journal if e["tool"] == "Bash")
        write_count = total - bash_count

        return [
            Violation(
                rule_id=self.id,
                message=(
                    f"Operation journal: {total} operations this session "
                    f"({bash_count} shell, {write_count} file writes)"
                ),
                severity=self.severity,
                suggestion="Full journal available in session_state['operation_journal'] for replay/audit.",
            )
        ]
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/packs/test_autopilot_post.py -v
```

**Step 5: Add to `__init__.py`** (update count to 6 in loads test)

```python
from agentlint.packs.autopilot.operation_journal import OperationJournal

RULES = [
    ProductionGuard(),
    DestructiveConfirmationGate(),
    DryRunRequired(),
    BashRateLimiter(),
    CrossAccountGuard(),
    OperationJournal(),
]
```

**Step 6: Commit**

```bash
git commit -am "feat(autopilot): add operation-journal rule"
```

---

## Task 8: Wire up detector + config + docs

**Files:**
- Modify: `src/agentlint/config.py` — add `"autopilot"` to `_DISABLED_BY_DEFAULT` (opt-in like security, don't auto-detect)
- Modify: `src/agentlint/detector.py` — no changes needed (autopilot is not auto-detected)
- Modify: `README.md` — add `autopilot` row to the Rule Packs table
- Modify: `CHANGELOG.md` — add v0.7.0 entry

Wait — `autopilot` should NOT be in `_DISABLED_BY_DEFAULT` because that set is for individual rules, not packs. The pack just needs to NOT appear in `detect_stack()`. It already won't — `detect_stack` only adds `security` if explicitly listed in config. The pack being in `PACK_MODULES` is enough; users add it manually.

**Step 1: Update README pack table**

In `README.md`, find the pack table and add:
```markdown
| **autopilot** | 6 | Opt-in (add `autopilot` to packs) |
```

Update "42 rules across 7 packs" → "48 rules across 8 packs" in the description line.

**Step 2: Update CHANGELOG.md**

Add at the top under `## Unreleased` or a new `## v0.7.0` section:
```markdown
## v0.7.0 — Autopilot Safety Pack

### New: `autopilot` pack (6 rules, opt-in)

- `production-guard` — Blocks Bash commands targeting production databases, gcloud projects, and AWS accounts. Configurable allowlists.
- `destructive-confirmation-gate` — Blocks DROP DATABASE, terraform destroy, kubectl delete namespace, and gcloud project delete unless `session_state['confirmed_destructive_ops']` contains an explicit acknowledgment.
- `dry-run-required` — Requires --dry-run/--check/plan preview before terraform apply, kubectl apply, ansible-playbook, and helm upgrade.
- `bash-rate-limiter` — Circuit-breaks after N destructive commands within a time window, preventing runaway autonomous loops.
- `cross-account-guard` — Warns when the agent switches between cloud projects or AWS profiles mid-session.
- `operation-journal` — Records every Bash and file-write operation to an audit log in session state; emits a summary at Stop.

### Rule count
48 rules across 8 packs (was 42/7).
```

**Step 3: Update agentlint-plugin README**

In `/Users/maupr92/Projects/agentlint-plugin/README.md`, update:
- "42 rules across 7 packs" → "48 rules across 8 packs"
- Add `autopilot` row to pack table

**Step 4: Verify full test suite passes**

```bash
cd /Users/maupr92/Projects/agentlint
uv run pytest -v --tb=short 2>&1 | tail -20
```
Expected: All pass, no regressions.

**Step 5: Commit docs**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: update README and CHANGELOG for v0.7.0 autopilot pack"
```

---

## Task 9: Integration test + branch cleanup

**Files:**
- Create: `tests/packs/test_autopilot_integration.py`

**Step 1: Write integration test**

```python
"""Integration test: autopilot pack loaded via full engine pipeline."""
from __future__ import annotations

from agentlint.models import HookEvent, RuleContext, Severity
from agentlint.packs import load_rules


def test_autopilot_pack_has_six_rules():
    rules = load_rules(["autopilot"])
    assert len(rules) == 6
    rule_ids = {r.id for r in rules}
    assert rule_ids == {
        "production-guard",
        "destructive-confirmation-gate",
        "dry-run-required",
        "bash-rate-limiter",
        "cross-account-guard",
        "operation-journal",
    }


def test_production_guard_blocks_via_engine():
    """End-to-end: production-guard fires through load_rules path."""
    rules = load_rules(["autopilot"])
    pg = next(r for r in rules if r.id == "production-guard")
    ctx = RuleContext(
        event=HookEvent.PRE_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "psql -h prod-db.internal -d myapp -U admin"},
        project_dir="/tmp/project",
        config={},
    )
    violations = pg.evaluate(ctx)
    assert len(violations) == 1
    assert violations[0].severity == Severity.ERROR


def test_operation_journal_records_across_events():
    """End-to-end: journal records PostToolUse and reports at Stop."""
    rules = load_rules(["autopilot"])
    oj = next(r for r in rules if r.id == "operation-journal")
    state = {}

    post_ctx = RuleContext(
        event=HookEvent.POST_TOOL_USE,
        tool_name="Bash",
        tool_input={"command": "gcloud projects list"},
        project_dir="/tmp/project",
        config={},
        session_state=state,
    )
    oj.evaluate(post_ctx)

    stop_ctx = RuleContext(
        event=HookEvent.STOP,
        tool_name="",
        tool_input={},
        project_dir="/tmp/project",
        config={},
        session_state=state,
    )
    violations = oj.evaluate(stop_ctx)
    assert len(violations) == 1
    assert "1 operations" in violations[0].message
```

**Step 2: Run the integration tests**

```bash
uv run pytest tests/packs/test_autopilot_integration.py -v
```
Expected: PASS

**Step 3: Run full suite with coverage**

```bash
uv run pytest --cov=agentlint --cov-report=term-missing 2>&1 | tail -30
```
Expected: All tests pass, coverage ≥ 95%

**Step 4: Final commit**

```bash
git add tests/packs/test_autopilot_integration.py
git commit -m "test(autopilot): add integration tests for full pack"
```

---

## Verification Checklist

```bash
# 1. All tests pass (including new)
uv run pytest -v --tb=short

# 2. Coverage check
uv run pytest --cov=agentlint --cov-report=term-missing | tail -5

# 3. Smoke test: production-guard blocks via CLI
echo '{"tool_name":"Bash","tool_input":{"command":"psql -h prod-db.example.com -d myapp"}}' | \
  CLAUDE_SESSION_ID=test uv run python -m agentlint check --event PreToolUse --project-dir /tmp

# 4. Smoke test: autopilot pack loads
uv run python -c "from agentlint.packs import load_rules; r = load_rules(['autopilot']); print(f'{len(r)} rules: {[x.id for x in r]}')"
```
