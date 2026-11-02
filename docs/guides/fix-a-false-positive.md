---
description: Find the rule and policy behind an AgentLint finding, then choose a narrow, reviewable correction or exemption.
---

# Fix a false positive

A finding should help your agent take its next step. When it flags legitimate work, first identify the rule and policy that produced it, then change the smallest relevant scope.
An exception for one file should not remove protection from the rest of the repository.

## 1. Read the finding

Check the rule ID, severity, operation, and policy source.
Under standard severity, an ERROR can deny a pre-tool action; a WARNING provides advice.
A post-tool finding reports on work that has already happened.

```bash
agentlint status
agentlint doctor
```

`status` shows the selected project, policy layers, and required rules. `doctor` checks common configuration problems without changing files.
If a workspace or organization policy owns the finding, review it with the person who maintains that policy.
Local approvals and exceptions cannot relax required or organization rules.

## 2. Check whether the suggested correction fits

For example, `max-file-size` may be right about a source module that has grown too large.
Splitting that module can be a better response than changing the limit.
If the file is generated and its size is intentional, a path exemption is more useful.

Look up the rule in the [reference](../rules.md) before changing configuration: some rules have specific allowances, and a rule's defaults may differ from the project's severity mode.

## 3. Pick the narrowest adjustment

| Need | Adjustment |
|---|---|
| One rule is wrong for generated files | A rule-specific `allow_paths` entry |
| One source file deliberately follows a different convention | A rule-specific inline ignore with a reason |
| One reviewed shell command needs an exception | An exact-command [exception](../configuration.md#exceptions), expiring within seven days |
| A person approves a class of action temporarily | A human-issued [approval](../approvals-and-evidence.md#approvals), expiring within 24 hours |
| An advisory rule is noisy for the rest of this session | `agentlint suppress <rule>`; ERROR findings remain unsuppressed |
| A rule does not belong in this project | Disable that rule in `agentlint.yml` |

To exempt generated files from the line limit:

```yaml
# Merge into the existing rules mapping in agentlint.yml.
rules:
  max-file-size:
    allow_paths:
      - "src/generated/*"
```

This skips only `max-file-size` for matching paths. Other content and security rules continue to run.
Globs use `fnmatch` and can match the full path, project-relative path, or file name.
Review rule-specific path exemptions carefully: required workspace rules can still honor them.

For a source file with an intentional convention:

```python
# agentlint:ignore max-file-size reason="generated parser; regenerate from grammar"
```

This form suppresses that rule throughout the file, not just the line below it.
For a located finding on one line, use `# agentlint:ignore-next-line`.
Required rules are not removed by inline ignores.

## 4. Recheck the original operation

Retry the same proposed change through your agent, or use [patch previews](../diagnostics.md#patch-previews) for a Codex patch.
Confirm that the intended finding is gone and other rules still report normally.
Configuration is loaded on subsequent checks; hook reinstallation is unnecessary for ordinary policy edits.

If the rule still looks wrong, [open an issue](https://github.com/mauhpr/agentlint/issues) with your AgentLint version, agent, rule ID, a minimal redacted example, and the expected result.
Use [diagnostics](../diagnostics.md) to capture a sanitized bundle when needed.

Read [Configuration](../configuration.md) for all exemption mechanisms, or [shared policies](shared-policy.md) if several repositories need the same adjustment.
