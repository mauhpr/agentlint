# Fintech Pack Specification

## Overview
The `fintech` pack provides rules for enforcing financial code safety patterns in Python projects. It is designed for fintech platforms handling monetary calculations, payment processing, and financial data.

## Pack Type
- **Opt-in** — not auto-detected. Enabled via `agentlint.yml`:
  ```yaml
  packs:
    - fintech
  ```

## Rules (5)

| ID | Severity | Event | Description |
|---|---|---|---|
| `fintech/no-float-for-money` | ERROR | PostToolUse | Prevents float/double for monetary values |
| `fintech/decimal-division-safety` | WARNING | PostToolUse | Requires explicit rounding on monetary division |
| `fintech/sensitive-data-exposure` | ERROR | PreToolUse | Blocks unmasked PII in logs/errors |
| `fintech/migration-safety` | ERROR | PreToolUse | Validates Alembic migration safety |
| `fintech/webhook-idempotency` | WARNING | PostToolUse | Ensures webhook handlers are idempotent |

## Motivation
Generic Python linters (ruff, mypy, flake8) catch syntax and type errors but miss domain-specific financial invariants:
- A `float` variable is valid Python but a financial bug waiting to happen
- An Alembic migration that drops a column passes all linters but may destroy financial records
- A webhook handler without idempotency is functionally correct but processes payments twice

These rules encode financial domain knowledge into automated enforcement.

## Target Users
- Fintech platforms (payment processors, lending platforms, trading systems)
- Any Python project handling monetary values with regulatory requirements
- Projects using Alembic for database migrations with financial data

## Dependencies
- No additional dependencies beyond agentlint core
- Rules use regex-based pattern matching (within agentlint's hook timeout constraints)

## Related Packs
- `security` — complements with credential/secret detection
- `python` — complements with Python-specific patterns
- `quality` — provides baseline code quality rules

## Version History
- v0.1.0 (planned) — Initial release with 5 rules
