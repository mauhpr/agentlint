# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.3.x   | Yes       |
| 0.2.x   | Yes       |
| 0.1.x   | No        |

## Reporting a vulnerability

If you discover a security vulnerability in AgentLint, please report it responsibly.

**Do not open a public GitHub issue.**

Instead, email **mauricio_perez_r@hotmail.com** with:

- A description of the vulnerability
- Steps to reproduce
- Potential impact

## Response timeline

- **Acknowledgment**: within 48 hours
- **Initial assessment**: within 1 week
- **Fix or mitigation**: as soon as practical, depending on severity

We will coordinate disclosure with you and credit you in the release notes (unless you prefer otherwise).

---

## Why these rules matter

AI coding agents are powerful but imperfect. They operate with broad tool access and can cause real damage when guardrails are missing. These incidents are not hypothetical.

### Secret leaks in generated code

Agents trained on code that includes API keys may reproduce those patterns. A widely-reported incident involved an agent writing `sk_live_` Stripe keys into committed source code, resulting in charges exceeding $30,000 before the key was revoked.

**AgentLint rules:** `no-secrets` (blocks 15+ token patterns), `no-env-commit` (blocks `.env` writes)

### Bash escape hatches (GitHub #16461)

When Write/Edit tools are restricted, agents bypass guardrails by writing files through Bash: `cat > file.py << EOF`, `echo "content" > file.py`, `tee file.py`, etc. This is the most common escape pattern in Claude Code.

**AgentLint rules:** `no-bash-file-write` (security pack, blocks 12+ write patterns)

### Destructive commands

Agents occasionally run `rm -rf` on the wrong directory, wipe databases with `DROP TABLE`, or force-push over main branch history. One documented case involved an agent running `rm -rf ~`, destroying the user's home directory.

**AgentLint rules:** `no-destructive-commands` (catastrophic patterns return ERROR), `no-force-push`

### Test suite weakening

Agents may "fix" failing tests by adding `@pytest.mark.skip`, replacing assertions with `assert True`, or commenting out failing checks. This passes CI but silently removes test coverage.

**AgentLint rules:** `no-test-weakening`

## Security pack

The `security` pack is opt-in because its rules are opinionated and may produce false positives in workflows that legitimately use Bash for file operations (e.g., build scripts, deployment pipelines).

Enable it when:
- You are working on security-sensitive projects
- You want maximum protection against agent escape hatches
- You are running agents with broad tool access

```yaml
packs:
  - universal
  - security
```
