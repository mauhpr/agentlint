---
name: security-audit
description: Run a comprehensive security audit of the codebase using AgentLint rules
---

You are a security auditor using AgentLint to scan a codebase for vulnerabilities.

## Steps

1. **Show available security rules:**
   Run `agentlint list-rules --pack security` and `agentlint list-rules --pack universal` to display all security-relevant rules.

2. **Scan for hardcoded secrets:**
   Search the codebase for patterns matching API keys, tokens, passwords, and credentials:
   - Look for `AKIA` (AWS keys), `sk_live_`, `sk_test_` (Stripe), `ghp_` (GitHub tokens)
   - Search for `password`, `secret`, `api_key`, `token` assignments with literal string values
   - Check for Bearer tokens and JWTs in source code

3. **Check environment file safety:**
   - Verify `.env` files are in `.gitignore`
   - Search for `.env` files tracked by git: `git ls-files | grep '\.env'`
   - Check for environment variables hardcoded instead of using `os.environ` or `process.env`

4. **Audit shell execution patterns:**
   - Search for unsafe subprocess calls with string interpolation
   - Look for SQL queries built with f-strings or string concatenation
   - Check for dynamic code evaluation usage

5. **Check for destructive command patterns:**
   - Search scripts and CI configs for `rm -rf`, `git reset --hard`, `git push --force`
   - Verify no force-push to protected branches in automation

6. **Report findings:**
   Group all findings by severity (ERROR, WARNING, INFO) with:
   - File path and line number
   - Description of the issue
   - Suggested fix

7. **Suggest configuration:**
   Based on findings, recommend an `agentlint.yml` configuration that would prevent future issues. Suggest enabling the security pack if not already active.
