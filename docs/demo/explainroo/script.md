# AgentLint: guardrails for AI coding agents

> Illustrated hook demonstration using a non-functional synthetic credential.
> Its value is masked on screen and omitted from saved evidence. All operations
> are evaluated as data: no proposed file writes or commands are executed.
> Decisions use core packs and standard severity in an isolated configuration.

## intro {hold=0.6 min=8}
[#product] AgentLint adds local guardrails to your coding agent. [#checks] It checks file changes and shell commands before they run.

## problem {hold=0.6 min=8}
[#risk] A coding agent can accidentally expose credentials or [#delete] delete important files. [#boundary] Project rules catch risky actions before execution.

## block {hold=0.6 min=10}
[#propose] Here, the agent tries to hard-code a credential. [#deny] AgentLint blocks the change and [#guidance] explains how to fix it.

## recover {hold=0.6 min=10}
[#correct] The agent uses an environment variable instead. [#allow] The corrected change is allowed. [#continue] Work continues within your rules.

## features {hold=0.7 min=10}
[#local] Checks run locally, with [#rules] configurable rule packs and [#ci] {CI|C I} support. [#agents] Connect Claude Code, Codex, Cursor, or another supported agent.

## install {hold=0.8 min=7}
[#install] Install AgentLint, [#connect] connect your agent, [#verify] and verify the hook. [#link] Follow the quickstart.
