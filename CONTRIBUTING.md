# Contributing to AgentLint

## Code of Conduct

By participating, you agree to follow our [Code of Conduct](CODE_OF_CONDUCT.md).
Report conduct concerns privately using the contact method documented there.

## First time here?

1. Fork and clone the repository.
2. Install and run the tests (see [Development setup](#development-setup)).
   Everything should pass.
3. Read a small rule. `src/agentlint/packs/universal/no_env_commit.py` shows the
   full pattern: class attributes, `evaluate()`, and handling of both file
   tools and shell commands.
4. Add a test case for an existing rule, for example in
   `tests/packs/test_universal_pre.py`.
5. Run the full checks again.

Then pick an issue or propose a new rule.

## Development setup

You need Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/mauhpr/agentlint.git
cd agentlint
uv sync --extra dev
```

## Checks

CI runs these on every PR. Run them before pushing:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

Use `uv run ruff format .` to apply formatting. For a coverage report:

```bash
uv run pytest --cov=agentlint --cov-report=term-missing
```

Coverage must stay at or above 95% (`fail_under` in `pyproject.toml`).

## Code style

- Python 3.11+ with `from __future__ import annotations`.
- Type hints on function signatures.
- Docstrings on public classes and functions.
- `ruff` formatting and linting are required; configuration is in
  `pyproject.toml`.

## Adding a rule

1. Create `src/agentlint/packs/<pack>/<rule_name>.py`.
2. Subclass `Rule` from `agentlint.models`.
3. Set `id`, `description`, `severity`, `events` and `pack`.
4. Implement `evaluate(self, context: RuleContext) -> list[Violation]`.
5. Add an instance to the pack's `RULES` list in its `__init__.py`.
6. Add tests in `tests/packs/`.
7. Document it in `docs/rules.md` (see [Documentation](#documentation)).

### Choosing the event

| Event | Use when |
|-------|----------|
| `PRE_TOOL_USE` | You need to **block** an action before it happens |
| `POST_TOOL_USE` | You need to **analyze** file content after a write or edit |
| `USER_PROMPT_SUBMIT` | You need to check the user's prompt |
| `SUB_AGENT_START` | You need to inject context into a starting subagent |
| `SUB_AGENT_STOP` | You need to audit a finished subagent |
| `STOP` | You need to report session-level results or scan changed files |

See [docs/custom-rules.md](docs/custom-rules.md#events) for all events and the
`RuleContext` fields.

### Rule guidelines

- Keep rules fast (under 10 ms per evaluation).
- Return an empty list to pass, a list of `Violation` to fail.
- Read per-rule options with `context.config.get(self.id, {})`.
- Avoid I/O in `PreToolUse` rules; they are on the critical path.
- Use `session_state` for state across calls.
- Built-in rules match Claude Code tool names (`Bash`, `Write`, `Edit`). Test
  with payloads from the agents you claim to support.

## Adding a pack

1. Create `src/agentlint/packs/<pack_name>/`.
2. Add `__init__.py` with a `RULES` list.
3. Register it in `PACK_MODULES` in `src/agentlint/packs/__init__.py`.
4. Update auto-detection in `src/agentlint/detector.py` if applicable.
5. Add it to `PACK_ORDER` and `PACK_ACTIVATION` in `scripts/gen_docs.py`.
6. Add tests in `tests/packs/`.

## Adding an agent

Follow [docs/custom-adapters.md](docs/custom-adapters.md). An adapter has to be
registered in several places; the page lists all of them.

## Documentation

User docs live in [`docs/`](docs/README.md). `tests/test_docs.py` enforces:

- `docs/rules.md` has a section headed `` ### `<rule-id>` `` for every
  built-in rule.
- The generated parts of `docs/rules.md` (pack tables) and `docs/cli.md` are
  current. Regenerate them after changing rules or CLI commands:

  ```bash
  uv run python scripts/gen_docs.py
  ```

- Relative links and `#anchors` in every Markdown file resolve.

Update the docs in the same PR as the behavior change, and add an entry to
`CHANGELOG.md`.

## Pull requests

- One feature or fix per PR.
- Include tests for new code.
- Update docs and `CHANGELOG.md` if behavior changes.
- Keep commits focused.

Maintainers: the release process is in [RELEASE.md](RELEASE.md).
