# AgentLint Architecture

AgentLint is a local-first guardrail engine for AI coding agents. The core package is agent-agnostic: adapters translate each tool's hook or guardrail payload into one normalized event shape, then the same rule engine evaluates it.

## System Map

```mermaid
flowchart LR
  Agent[AI coding agent<br/>Claude, Cursor, Codex, Gemini, Continue, Kimi, Grok, OpenAI, MCP] --> Adapter[Platform adapter]
  Adapter --> Event[Normalized AgentEvent<br/>+ NormalizedTool]
  Event --> Config[agentlint.yml<br/>stack, packs, rules]
  Config --> Engine[Rule engine]
  Engine --> Rules[Rule packs]
  Rules --> Result[Allow, block, warn, or report]
  Result --> Formatter[Platform formatter]
  Formatter --> Agent
```

## Adapter Layer

```mermaid
flowchart TB
  Raw[Native payload] --> Detect[Adapter selection]
  Detect --> Claude[Claude Code]
  Detect --> Cursor[Cursor]
  Detect --> Codex[Codex]
  Detect --> Gemini[Gemini]
  Detect --> Continue[Continue]
  Detect --> Kimi[Kimi]
  Detect --> Grok[Grok]
  Detect --> OpenAI[OpenAI Agents SDK]
  Detect --> MCP[MCP hosts]
  Detect --> Generic[Generic HTTP]
  Claude --> Normalized[RuleContext]
  Cursor --> Normalized
  Codex --> Normalized
  Gemini --> Normalized
  Continue --> Normalized
  Kimi --> Normalized
  Grok --> Normalized
  OpenAI --> Normalized
  MCP --> Normalized
  Generic --> Normalized
```

Adapters own platform-specific details:

- Native event names.
- Tool-name mapping.
- Hook installation and uninstall.
- Output formatting expected by the agent.
- Project directory resolution.

Rules should not know which AI tool invoked them.

## Rule Evaluation

```mermaid
sequenceDiagram
  participant Hook as Agent hook/guardrail
  participant CLI as agentlint CLI
  participant Adapter as Adapter
  participant Engine as Engine
  participant Pack as Rule packs
  participant Agent as Agent

  Hook->>CLI: JSON payload on stdin
  CLI->>Adapter: translate event + tool payload
  Adapter->>Engine: RuleContext
  Engine->>Pack: evaluate matching rules
  Pack-->>Engine: violations
  Engine-->>CLI: result
  CLI-->>Agent: platform-specific allow/block/warn response
```

ERROR rules can block an action. WARNING rules advise the agent. INFO rules show in reports. The circuit breaker can degrade noisy rules over a session, but security-critical rules remain blocking.

## Configuration Flow

```mermaid
flowchart LR
  Project[Project files] --> Detect[Stack detection]
  Detect --> Packs[Active packs]
  Config[agentlint.yml] --> Packs
  AGENTS[AGENTS.md] --> Detect
  Packs --> Rules[Loaded rules]
  Custom[.agentlint/rules] --> Rules
```

`stack: auto` activates packs from project files. Explicit `packs:` entries override auto-detection. Rule-level configuration lives under `rules:`.

## AgentChute Opt-In

```mermaid
flowchart LR
  Engine[Local AgentLint result] --> Queue[Durable local queue]
  Queue --> Flush[agentlint agentchute flush]
  Flush --> API[AgentChute API]
  API --> Dashboard[Team dashboard]
  API --> Feeds[Hybrid security feeds]
  Feeds --> Rules[Cloud-assisted local rules]
```

AgentChute is disabled unless a license key and opt-in are present. The queue sends privacy-safe event summaries only: rule IDs, severity, timestamps, tool name, session metadata, and sanitized summaries. It does not send raw file contents, full prompts, or full edit strings.

## Plugin Repo Relationship

```mermaid
flowchart TB
  Plugin[agentlint-plugin<br/>Claude Code marketplace wrapper] --> Resolver[resolve-and-run.sh]
  Resolver --> Package[agentlint Python package]
  Package --> Engine[Core engine]
  Package --> Adapters[All platform adapters]
```

The plugin repo is not the core product. It is the Claude Code marketplace packaging layer. All rules, adapters, AgentChute sync, and CLI behavior live in the `agentlint` Python package.

## Release Boundary

For a release, test these surfaces separately:

- Core rule engine and adapter tests: `uv run pytest`.
- Package metadata and install behavior.
- Claude Code plugin metadata and binary resolver.
- Local AgentLint-to-AgentChute integration smoke from the AgentChute repo.
