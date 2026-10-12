# AgentLint: check before the action

> Illustrated hook demonstration with example commands. The commands are
> inspected as data and are never executed. Decisions are captured from
> AgentLint's built-in rules using a standard isolated configuration.

## hook {hold=0.6 min=7}
[#agent] Your coding agent can edit files and run commands. [#check] AgentLint checks proposed actions before they reach your repository.

## block {hold=0.8 min=9}
[#command] Here, the agent proposes a force push to the main branch. [#deny] The hook blocks it [#reason] and explains the safer next step.

## recover {hold=0.7 min=9}
[#inspect] The agent can inspect the diff, [#push] then push to a feature branch. [#allow] AgentLint checks the new command and lets it through when no blocking rule matches.

## policy {hold=0.7 min=8}
[#errors] Errors block actions. [#warnings] Warnings stay advisory. [#review] Configure the rules for your project, and keep code review and continuous integration in your workflow.

## install {hold=1.3 min=10}
[#install] Install AgentLint [#connect] and connect your coding agent. [#verify] Verify the hook is running. [#link] The quickstart includes setup guides for Claude Code, Codex, and other agents.
