---
title: AgentLint Documentation Revamp - Plan
type: docs
date: 2026-11-02
artifact_contract: ce-unified-plan/v1
product_contract_source: ce-plan-bootstrap
execution: code
---

# AgentLint Documentation Revamp - Plan

## Goal Capsule

Make AgentLint understandable on a first visit and useful through setup, a first correction, everyday policy tuning, and extension.
The deliverable is a verified local documentation change set across the core and Claude plugin repositories.
Publishing and changes to guardrail behavior are outside this work.

## Product Contract

### Problem Frame

AgentLint has substantial reference material, but its first-use story stops at a refusal, its README implies broader enforcement than the integrations provide, and users must translate component names into solutions to their problems.

### Requirements

**First use**

- R1. The README and homepage show a proposed mistake, the finding, and a useful correction before detailed feature inventories.
- R2. The quickstart completes installation, agent-specific activation, observation, a synthetic check, and a corrected action.
- R3. Coverage distinguishes native hook enforcement, SDK guardrails, advisory MCP checks, warnings, and opt-in packs.

**Learning and reference**

- R4. Task guides cover protected branches, false positives, external linters, and shared repository policies using existing capabilities.
- R5. Key rule examples show triggers, defaults, corrections, and limitations without claiming universal detection.
- R6. Existing rule IDs, generated sections, and externally linked page paths and anchors remain usable.

**Consistency and delivery**

- R7. Support information, package documentation links, plugin messaging, contributor instructions, and machine-readable documentation agree with the current package.
- R8. Documentation builds strictly and existing documentation and rule checks pass.

### Scope Boundaries

Retain MkDocs Material and the existing cream/green visual identity.
Do not change the rule engine, hook installation, severity defaults, runtime dependencies, release version, or cloud policy.
Do not invent performance measurements, adoption claims, testimonials, or host-version guarantees.

## Planning Contract

### Key Technical Decisions

- KTD1. Improve the existing MkDocs site rather than replacing its framework (session-settled: user-approved — chosen over a framework migration: the audit found the existing platform sufficient).
- KTD2. Keep the generated rule tables and CLI reference as authoritative inventories; add human-authored examples and task guides around them. Governs R5 and R6.
- KTD3. Add a code-native SVG explanation of the correction loop, retaining the existing product video and poster. This supplies immediate proof without requiring video playback. Governs R1.
- KTD4. Use source and existing tests to verify examples; use strict site builds and rendered HTML inspection for the documentation interface. No new runtime behavior means no new runtime unit tests are required. Governs R8.

### Assumptions

The current package is 2.10.1 and the documented security policy intends support for the latest minor series.
The existing branch contains a pre-existing unpushed README commit; retain it and do not publish the branch.
Browser screenshot tools may be unavailable; in that case record the limitation and inspect responsive layout and built HTML directly.

## Implementation Units

### U1. First-use story and navigation

- Files: `README.md`, `docs/README.md`, `docs/quickstart.md`, `docs/assets/`, `mkdocs.yml`, `docs/llms.txt`, `pyproject.toml`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`.
- Requirements: R1, R2, R3, R7, R8.
- Approach: concise proof first; explicit agent activation; local and optional-cloud boundaries; task-oriented navigation; absolute published documentation links in the package README.
- Verification: existing docs/inventory checks, generated-document check, strict MkDocs build, SVG parsing, built-page links and responsive CSS inspection.
- Test expectation: no new runtime tests; editorial and configuration changes use existing checks and build verification.

### U2. Task guides and diagnostic entry point

- Files: `docs/guides/`, `docs/diagnostics.md`, `docs/configuration.md`, `docs/ci.md`, `docs/approvals-and-evidence.md`.
- Requirements: R3, R4, R6.
- Approach: four complete guides built from existing config and commands; local hook troubleshooting first; retain existing reference anchors and advanced details.
- Verification: source-backed command/config checks and the shared docs link/build checks after integration.
- Test expectation: no new runtime tests; examples document existing behavior.

### U3. Rule reference examples and integration clarity

- Files: `docs/rules.md`, `docs/agents/`, `docs/architecture.md`, `docs/subagent-safety.md`, `docs/mcp.md`, `docs/custom-rules.md`, `docs/custom-adapters.md`, `docs/agentchute.md`.
- Requirements: R3, R5, R6.
- Approach: deepen representative rules and clarify enforcement boundaries at each integration; preserve existing technical reference detail and generated content.
- Verification: verify examples against owning implementations/tests; generated-document and link checks after integration.
- Test expectation: use existing rule tests unchanged.

### U4. Plugin entry point and integrated verification

- Files: `../agentlint-plugin/README.md` plus integration corrections in files owned above.
- Requirements: R1, R3, R7, R8.
- Approach: keep install and compatibility concise, surface plugin tools, route reference readers to canonical docs, then verify the whole change set.
- Dependencies: final verification follows U1, U2, and U3.
- Verification: core doc checks, selected existing rule checks, strict build, diff review, and plugin-relative link checks.

## Verification Contract

- `tests/test_docs.py` and `tests/test_rule_inventory.py` pass.
- `scripts/gen_docs.py --check` reports current generated content.
- Existing relevant universal-rule tests pass unchanged.
- `mkdocs build --strict` succeeds with locked documentation dependencies.
- New guide links, old anchors, local media, and site navigation resolve in generated HTML.
- No unrelated local files, runtime code changes, secret values, or fabricated benchmarks enter the change set.

## Definition of Done

All requirements are represented in the final docs, examples agree with existing defaults, generated references remain current, and verification succeeds.
Report the local changes and any browser verification limitation without claiming deployment.
