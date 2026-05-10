# AgentLint 2.1.0 Release Plan

Goal: release AgentLint 2.1.0 as the first customer-testable multi-agent + AgentChute-ready OSS package.

## Release Scope

- Multi-agent positioning in docs: Claude Code, Cursor, Codex, Gemini, Continue, Kimi, Grok, OpenAI Agents, MCP, and generic adapters.
- AgentChute opt-in setup via `agentlint init --team-key=...` without writing plaintext keys to repo config.
- Hybrid AgentChute security feeds and privacy-safe event queue.
- Cloud-assisted rules that self-degrade when no AgentChute key is configured.
- Rule inventory and adapter test coverage locked before publishing.

## Pre-Release Checklist

1. Run the full AgentLint test suite:

   ```bash
   uv run pytest
   ```

2. Verify package metadata:

   ```bash
   uv run python -m build
   ```

3. Smoke the key setup flow:

   ```bash
   agentlint init --team-key=ac_team_test_x
   ```

4. Verify adapter docs exist:

   - `docs/setup-claude.md`
   - `docs/setup-cursor.md`
   - `docs/setup-codex.md`
   - `docs/setup-gemini.md`
   - `docs/setup-continue.md`
   - `docs/setup-kimi.md`
   - `docs/setup-grok.md`
   - `docs/setup-openai.md`
   - `docs/setup-mcp.md`
   - `docs/setup-generic.md`

5. Run the local AgentChute integration smoke from the AgentChute repo while its API is running:

   ```bash
   cd ../agentlint-teams
   make agentlint-integration
   ```

6. Update version:

   - `pyproject.toml` -> `2.1.0`
   - changelog/release notes -> `2.1.0`

7. Publish to PyPI only after the above passes.

## Release Notes Draft

AgentLint 2.1.0 makes AgentLint a multi-agent guardrail layer, not only a Claude Code hook package. It adds clearer setup paths for Cursor, Codex, Gemini, Continue, Kimi, Grok, OpenAI Agents, MCP hosts, and custom frameworks, plus AgentChute opt-in setup for team dashboards, licensed feeds, and privacy-safe event sync.

## Do Not Release Until

- The docs no longer present Claude Code as the default mental model.
- `uv run pytest` passes.
- The local AgentLint-to-AgentChute smoke passes with the local API.
- The plugin repo has a matching 2.1.0 release plan and version bump.
