# Contributing to AgentLint

## First timer? Start here

1. **Fork and clone** the repository
2. **Run the tests**: `uv sync --dev && uv run pytest -v` — everything should pass
3. **Pick a rule to read**: Start with `src/agentlint/packs/universal/no_env_commit.py` — it's the simplest rule (~55 lines) and shows the full pattern
4. **Try a small change**: Add a test case to an existing rule in `tests/packs/test_universal_pre.py`
5. **Run tests again**: `uv run pytest -v --cov=agentlint` — verify your test runs and coverage stays above 95%

That's it! You now understand the full loop. Pick an issue or propose a new rule.

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

Coverage should stay at or above 95%.

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

### Choosing the right hook event

AgentLint supports all 17 Claude Code hook events. The most commonly used:

| Event | Use when |
|-------|----------|
| `PRE_TOOL_USE` | You need to **block** a dangerous action before it happens |
| `POST_TOOL_USE` | You need to **analyze** file content after a write/edit |
| `USER_PROMPT_SUBMIT` | You need to check/transform the user's prompt |
| `SUB_AGENT_START` | You need to inject context into a spawning subagent |
| `SUB_AGENT_STOP` | You need to audit a completed subagent's actions |
| `STOP` | You need to report session-level metrics or scan changed files |

See [docs/custom-rules.md](docs/custom-rules.md) for the full list of all 17 events.

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
