# Contributing to AgentLint

## Development setup

```bash
git clone https://github.com/mauhpr/agentlint.git
cd agentlint
uv sync --dev
```

## Running tests

```bash
uv run pytest -v
uv run pytest --cov=agentlint --cov-report=term-missing
```

Coverage should stay at or above 93%.

## Code style

- Python 3.11+ with `from __future__ import annotations`
- Type hints on function signatures
- Docstrings on public classes and functions
- `ruff` for formatting and linting (if configured)

## Adding a rule

1. Create `src/agentlint/packs/<pack>/<rule_name>.py`
2. Subclass `Rule` from `agentlint.models`
3. Set `id`, `description`, `severity`, `events`, `pack`
4. Implement `evaluate(self, context: RuleContext) -> list[Violation]`
5. Add the rule instance to the pack's `RULES` list in `__init__.py`
6. Add tests in `tests/packs/`

### Rule guidelines

- Rules should be fast (< 10ms per evaluation)
- Return an empty list for "pass", a list of `Violation` for "fail"
- Use `context.config.get(self.id, {})` for per-rule config options
- Avoid I/O in PreToolUse rules (they're on the critical path)
- Use `session_state` for cross-invocation tracking

## Adding a pack

1. Create `src/agentlint/packs/<pack_name>/`
2. Add `__init__.py` with a `RULES` list
3. Register in `PACK_MODULES` in `src/agentlint/packs/__init__.py`
4. Update auto-detection in `src/agentlint/detector.py` if applicable
5. Add tests in `tests/packs/`

## Pull requests

- One feature or fix per PR
- Include tests for new code
- Update docs if behavior changes
- Keep commits focused
