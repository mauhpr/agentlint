---
description: Feed Ruff or ESLint findings back to your coding agent after file writes with AgentLint's existing CLI integration.
---

# Run Ruff or ESLint after agent edits

AgentLint can run an existing linter after a supported file write or edit and return its findings to the agent.
You keep the tool's configuration and suppression comments; AgentLint connects the result to the agent's working session.

This is a **post-tool check**. It does not prevent the initial write or roll it back.
Confirm that the agent's post-tool hook is installed; pre-tool hooks also supply snapshots used for changed-line filtering.
See [hook coverage](../diagnostics.md#coverage-configured-enabled-observed).

## 1. Confirm the linter runs in your project

For a Python project that already uses Ruff:

```bash
uv run ruff check src/app.py --output-format=concise
```

For a JavaScript project that already installs ESLint locally:

```bash
./node_modules/.bin/eslint src/app.js --format stylish
```

Use a command that works from the repository root and is available in the environment that starts your coding agent.
AgentLint does not install these tools or provide their configuration.

## 2. Add a post-edit check

Merge the relevant command into `agentlint.yml`:

```yaml
rules:
  cli-integration:
    timeout: 3
    severity: warning
    diff_only: true
    commands:
      - name: ruff
        glob: "**/*.py"
        command: "uv run ruff check {file.path} --output-format=concise"
```

`cli-integration` belongs to the default `universal` pack. No extra AgentLint package is required.
The default tool filter is `Write` and `Edit`; the integration adapter maps supported native file tools to those names.
Commands run from the project directory, and AgentLint shell-escapes placeholder values such as `{file.path}`.

Keep the total check time below the host's post-tool hook timeout. Claude Code's native setup and marketplace plugin configure a 10-second `PostToolUse` timeout; the 3-second per-command limit above leaves room for AgentLint to start, run other rules, and return feedback.
Matching commands run sequentially, so budget their combined time, including any formatter. Set an explicit timeout for each added command or retain the rule-level timeout when replacing the Ruff entry below. For slower checks, increase the host hook timeout as well as the command timeout, or run the checks separately in CI. If the host terminates the hook first, the agent may receive no linter findings.

For ESLint, replace the command entry:

```yaml
rules:
  cli-integration:
    commands:
      - name: eslint
        glob: "**/*.js"
        command: "./node_modules/.bin/eslint {file.path} --format stylish"
        diff_only: false
```

Use additional entries with suitable globs for `.jsx`, `.ts`, or `.tsx` files and ensure the linter supports them.
ESLint's stylish output separates filenames and line numbers, so the example retains its complete output instead of relying on AgentLint's changed-line parser.

## 3. See feedback reach the agent

Ask your agent to make a small edit to a matching source file, then inspect the post-tool feedback.
A nonzero linter exit produces a finding named `cli-integration/ruff` or `cli-integration/eslint`.
The configured warning advises the agent to correct the issue; it does not undo the edit.

For Ruff's concise `path:line:column` output, `diff_only: true` filters located findings to changed lines when both pre- and post-edit contents are available.
New files and edits without a pre-edit snapshot retain all findings. Unlocated failures remain visible.

If no check appears, verify the file glob, the installed post-tool hook, the linter command, and the agent's inherited `PATH`.
An unresolvable placeholder skips the command. A timeout or startup error is logged rather than emitted as a linter finding; run the command directly when investigating.

## Optional: format after each edit

For a deterministic formatter, add an entry with `mode: auto-fix`:

```yaml
      - name: ruff-format
        glob: "**/*.py"
        command: "uv run ruff format {file.path}"
        mode: auto-fix
```

This command changes the file after the agent's write. Success is silent; a nonzero exit produces a finding.
Review your diff as usual and keep CI checks for the final repository state.

Read the [`cli-integration` reference](../rules.md#cli-integration) for placeholders and per-command options, or [add AgentLint to CI](../ci.md).
