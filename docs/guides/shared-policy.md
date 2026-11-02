---
description: Apply a local AgentLint baseline across repositories, preserve required rules, and verify which policy each project receives.
---

# Share a policy across repositories

Use a workspace policy when several local repositories need the same baseline.
Repositories can keep their own language packs and rule options, while selected rules remain required.
This works locally without AgentChute.

## 1. Put the baseline above your repositories

For repositories at `/work/code/service-a` and `/work/code/service-b`, create `/work/code/agentlint.yml`:

```yaml
packs: [security]

workspace:
  required_rules:
    - no-secrets
    - no-env-commit
    - no-force-push
```

The policy applies only to projects inside the directory containing that file.
It does not affect repositories elsewhere on your machine.
Use a recognized AgentLint YAML filename and avoid competing configuration filenames in the same directory.

## 2. Point the agent at it

Set the path in the environment that starts your coding agent:

```bash
export AGENTLINT_WORKSPACE_CONFIG=/work/code/agentlint.yml
```

Restart the agent after changing its environment. Its hook processes inherit that environment.
Each repository still needs its own working [agent integration](../README.md#agents), or a user-scope hook installation that covers it.

## 3. Keep repository-specific settings

For example, `/work/code/service-a/agentlint.yml` can contain:

```yaml
packs: [python]
rules:
  max-file-size:
    limit: 400
```

Workspace and repository packs are additive, so this repository receives the shared security pack, its Python pack, and the default core packs.
Mappings merge recursively; repository scalars and lists replace workspace values for the same setting.

Required rules stay enabled even if a repository tries to disable them or omits their packs.
Their findings retain their policy severity: an ERROR stays blocking under supported pre-tool hooks, while a native WARNING remains advisory.
Required rules are not relaxed by severity mode, inline ignores, exact-command exceptions, human approvals, or the circuit breaker.
Per-rule path exemptions can still apply, so review those as part of your baseline.

## 4. Verify both repositories

```bash
agentlint status --project-dir /work/code/service-a
agentlint doctor --project-dir /work/code/service-a
agentlint status --project-dir /work/code/service-b
```

Confirm that each status report names the workspace policy and selected repository, lists the required rules, and reports hook observation for that project.
A recent observation from another repository is not evidence that hooks are running in this one.
Blocking findings name the policy layer that made the rule active.

For a project inside the workspace, a missing, invalid, or shadowed policy file produces a configuration error rather than silently dropping the shared baseline.
The environment variable does not apply the policy to projects outside the workspace directory.

## Use a directory mapping for a monorepo

One repository with several stacks can use `projects:` instead of separate workspace files:

```yaml
projects:
  web/:
    packs: [frontend, react]
  api/:
    packs: [python, security]
```

The longest matching directory prefix selects the file's packs; unmatched files use the top-level packs.
See [monorepo configuration](../configuration.md#monorepos).

Workspace policies depend on local configuration and hooks; they are not a tamper-proof sandbox.
Use [CI checks](../ci.md) for repository changes and server-side branch protection for Git operations.
For centrally distributed organization policy and team visibility, see [optional AgentChute](../agentchute.md).
