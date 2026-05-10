from __future__ import annotations

from agentlint.config import AgentLintConfig
from agentlint.models import HookEvent, Rule, RuleContext, Severity


class DummyRule(Rule):
    id = "dummy-rule"
    description = "dummy"
    severity = Severity.INFO
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext):  # pragma: no cover - not needed by loader tests
        return []


def test_load_installed_rules_accepts_single_and_iterable_and_skips_bad(monkeypatch):
    from agentlint import packs

    class EntryPoint:
        def __init__(self, name, factory):
            self.name = name
            self._factory = factory

        def load(self):
            if self.name == "raises-on-load":
                raise RuntimeError("load failed")
            return self._factory

    eps = [
        EntryPoint("single", lambda: DummyRule()),
        EntryPoint("iterable", lambda: [DummyRule(), object()]),
        EntryPoint("none", lambda: None),
        EntryPoint("raises-on-load", lambda: DummyRule()),
        EntryPoint("raises-on-call", lambda: (_ for _ in ()).throw(RuntimeError("call failed"))),
    ]
    monkeypatch.setattr(packs, "entry_points", lambda group: eps)

    rules = packs.load_installed_rules()

    assert [rule.id for rule in rules] == ["dummy-rule", "dummy-rule"]


def test_load_custom_rules_loads_rule_subclasses_and_ignores_bad_files(tmp_path):
    from agentlint import packs

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "_private.py").write_text("raise RuntimeError('skip me')\n", encoding="utf-8")
    (rules_dir / "bad.py").write_text("raise RuntimeError('bad custom rule')\n", encoding="utf-8")
    (rules_dir / "good.py").write_text(
        """
from agentlint.models import HookEvent, Rule, RuleContext, Severity

class LocalRule(Rule):
    id = "local-rule"
    description = "local"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "universal"

    def evaluate(self, context: RuleContext):
        return []
""",
        encoding="utf-8",
    )

    rules = packs.load_custom_rules("rules", str(tmp_path))

    assert [rule.id for rule in rules] == ["local-rule"]
    assert packs.load_custom_rules("missing", str(tmp_path)) == []


def test_load_project_rules_filters_installed_custom_and_policy(monkeypatch, tmp_path):
    from agentlint import packs

    custom_dir = tmp_path / "rules"
    custom_dir.mkdir()
    (custom_dir / "custom.py").write_text(
        """
from agentlint.models import HookEvent, Rule, RuleContext, Severity

class CustomRule(Rule):
    id = "custom-rule"
    description = "custom"
    severity = Severity.WARNING
    events = [HookEvent.PRE_TOOL_USE]
    pack = "custom"

    def evaluate(self, context: RuleContext):
        return []
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(packs, "load_rules", lambda active: [DummyRule()])
    monkeypatch.setattr(packs, "load_installed_rules", lambda: [DummyRule()])

    cfg = AgentLintConfig(packs=["universal"], custom_rules_dir="rules")
    assert [rule.id for rule in packs.load_project_rules(cfg, str(tmp_path), include_policy=False)] == [
        "dummy-rule",
        "dummy-rule",
    ]

    cfg = AgentLintConfig(packs=["universal", "custom"], custom_rules_dir="rules")
    with monkeypatch.context() as m:
        import agentlint.agentchute.policy as policy

        m.setattr(policy, "build_policy_rules", lambda: [DummyRule()])
        ids = [rule.id for rule in packs.load_project_rules(cfg, str(tmp_path))]

    assert ids == ["dummy-rule", "dummy-rule", "custom-rule", "dummy-rule"]


def test_load_project_rules_ignores_policy_loader_failures(monkeypatch):
    from agentlint import packs

    monkeypatch.setattr(packs, "load_rules", lambda active: [])
    monkeypatch.setattr(packs, "load_installed_rules", lambda: [])
    import agentlint.agentchute.policy as policy

    monkeypatch.setattr(policy, "build_policy_rules", lambda: (_ for _ in ()).throw(RuntimeError("bad policy")))

    assert packs.load_project_rules(AgentLintConfig(packs=["universal"]), "/tmp/project") == []
