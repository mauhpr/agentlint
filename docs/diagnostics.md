# Hook and policy diagnostics

`agentlint policy status` shows the cached policy version, active cached rule IDs,
whether those rules are enforced, credential presence, and whether AgentChute
connectivity has been checked. Add `--online` to make a read-only connection
probe. A missing key stops refresh and event delivery but does not silently
disable valid cached rules. Cache changes apply on the next hook invocation;
restart the coding agent after changing environment variables it inherited.

To reproduce a hook result and save a minimized diagnostic bundle, pipe the
original hook input to `agentlint check` with `--diagnostic-bundle`:

```sh
agentlint check --event PostToolUse --adapter codex \
  --diagnostic-bundle /tmp/agentlint-diagnostic.json < hook-input.json
```

The bundle contains adapter and AgentLint versions, event and tool type, input
field names, a redacted command operation and input hash, evaluated and fired rule IDs, and
the Codex output validation result. It omits raw command arguments, prompts,
file contents, paths, rule messages and credentials. Review the file before
sharing it. Diagnostic files are written with owner-only permissions.

New session recordings and AgentChute event summaries likewise omit raw Bash
arguments, prompt text, file paths, search queries, URLs and task descriptions.
Existing recordings made by older versions are **not** rewritten. Review or
delete old files with `agentlint recordings list` and `agentlint recordings clear`.

Read-only cloud detection accepts only simple allowlisted `gcloud` and `aws`
inspection forms, including literal `env NAME=value` wrappers. PostgreSQL
inspection through `psql -c` or a repository-local `psql -f` file is exempted
from production targeting only when the script explicitly starts with
`BEGIN READ ONLY`, contains only SELECT/SHOW/EXPLAIN SELECT statements, and
ends with COMMIT or ROLLBACK. Unknown syntax remains checked.
